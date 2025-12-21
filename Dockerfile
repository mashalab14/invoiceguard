# InvoiceGuard - Peppol BIS 3.0 Pre-flight Validator
# Base: Python 3.9 with Java 17
FROM python:3.9-slim-bookworm

# Set bash as default shell with strict error handling
SHELL ["/bin/bash", "-c"]

# Install system dependencies
RUN set -euo pipefail; \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        wget \
        unzip \
        git \
        findutils \
        openssl \
        bash \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Step 1: Install KoSIT Validator v1.5.0
RUN set -euo pipefail; \
    echo "[BUILD] Downloading KoSIT Validator 1.5.0..."; \
    wget -q https://github.com/itplr-kosit/validator/releases/download/v1.5.0/validator-1.5.0-distribution.zip -O /tmp/validator.zip; \
    echo "[BUILD] Extracting validator..."; \
    unzip -q /tmp/validator.zip -d /app/validator_dist; \
    rm /tmp/validator.zip; \
    echo "[BUILD] Locating standalone JAR (excluding java8)..."; \
    JAR_COUNT=$(find /app/validator_dist -type f -name "validationtool-*-standalone.jar" ! -name "*java8*" | wc -l); \
    echo "[BUILD] Found $JAR_COUNT matching JAR file(s)"; \
    if [ "$JAR_COUNT" -ne 1 ]; then \
        echo "[ERROR] Expected exactly 1 JAR file, found $JAR_COUNT"; \
        exit 1; \
    fi; \
    JAR_FILE=$(find /app/validator_dist -type f -name "validationtool-*-standalone.jar" ! -name "*java8*"); \
    echo "[BUILD] Moving JAR: $JAR_FILE -> /app/validator.jar"; \
    mv "$JAR_FILE" /app/validator.jar; \
    echo "[BUILD] Computing SHA256..."; \
    sha256sum /app/validator.jar; \
    rm -rf /app/validator_dist

# Step 2: Install Peppol Rules (release-3.0.18)
RUN set -euo pipefail; \
    echo "[BUILD] Cloning Peppol validator-configuration-bis release-3.0.18..."; \
    git clone --depth 1 --branch release-3.0.18 https://projekte.kosit.org/peppol/validator-configuration-bis.git /app/peppol_rules; \
    echo "[BUILD] Capturing commit hash for traceability..."; \
    git -C /app/peppol_rules rev-parse HEAD > /app/version_info.txt; \
    COMMIT_HASH=$(cat /app/version_info.txt); \
    echo "[BUILD] Rules Commit: $COMMIT_HASH"; \
    echo "[BUILD] Discovering scenarios.xml..."; \
    SCENARIOS_COUNT=$(find /app/peppol_rules -type f -name "scenarios.xml" | wc -l); \
    echo "[BUILD] Found $SCENARIOS_COUNT scenarios.xml file(s)"; \
    if [ "$SCENARIOS_COUNT" -ne 1 ]; then \
        echo "[ERROR] Expected exactly 1 scenarios.xml, found $SCENARIOS_COUNT"; \
        exit 1; \
    fi; \
    SCENARIOS_FILE=$(find /app/peppol_rules -type f -name "scenarios.xml"); \
    RULES_DIR=$(dirname "$SCENARIOS_FILE"); \
    echo "[BUILD] Rules directory: $RULES_DIR"; \
    echo "$RULES_DIR" > /app/rules_dir.txt; \
    echo "[BUILD] Validating directory layout..."; \
    if [ ! -d "$RULES_DIR/resources" ]; then \
        echo "[ERROR] resources folder not found in $RULES_DIR"; \
        exit 1; \
    fi; \
    echo "[BUILD] ✓ resources folder exists"; \
    if [ ! -d "/app/peppol_rules/test-files/good/ubl" ]; then \
        echo "[ERROR] test-files/good/ubl folder not found"; \
        exit 1; \
    fi; \
    echo "[BUILD] ✓ test-files/good/ubl folder exists"; \
    if [ ! -d "/app/peppol_rules/test-files/good/cii" ]; then \
        echo "[ERROR] test-files/good/cii folder not found"; \
        exit 1; \
    fi; \
    echo "[BUILD] ✓ test-files/good/cii folder exists"

# Step 3: Setup Test Data (Atomic Selection)
RUN set -euo pipefail; \
    echo "[BUILD] Selecting UBL test file..."; \
    UBL_FILE=$(find /app/peppol_rules -path '*/test-files/good/ubl/*.xml' | sort | head -n 1); \
    if [ -z "$UBL_FILE" ]; then \
        echo "[ERROR] No UBL test files found"; \
        exit 1; \
    fi; \
    echo "[BUILD] Selected UBL: $UBL_FILE"; \
    cp "$UBL_FILE" /app/test_ubl.xml; \
    UBL_SIZE=$(stat -c%s /app/test_ubl.xml 2>/dev/null || stat -f%z /app/test_ubl.xml); \
    if [ "$UBL_SIZE" -le 0 ]; then \
        echo "[ERROR] test_ubl.xml has invalid size: $UBL_SIZE"; \
        exit 1; \
    fi; \
    echo "[BUILD] ✓ test_ubl.xml size: $UBL_SIZE bytes"; \
    echo "[BUILD] Selecting CII test file..."; \
    CII_FILE=$(find /app/peppol_rules -path '*/test-files/good/cii/*.xml' | sort | head -n 1); \
    if [ -z "$CII_FILE" ]; then \
        echo "[ERROR] No CII test files found"; \
        exit 1; \
    fi; \
    echo "[BUILD] Selected CII: $CII_FILE"; \
    cp "$CII_FILE" /app/test_cii.xml; \
    CII_SIZE=$(stat -c%s /app/test_cii.xml 2>/dev/null || stat -f%z /app/test_cii.xml); \
    if [ "$CII_SIZE" -le 0 ]; then \
        echo "[ERROR] test_cii.xml has invalid size: $CII_SIZE"; \
        exit 1; \
    fi; \
    echo "[BUILD] ✓ test_cii.xml size: $CII_SIZE bytes"

# Copy application files
COPY requirements.txt /app/
COPY main.py /app/

# Install Python dependencies
RUN set -euo pipefail; \
    pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
