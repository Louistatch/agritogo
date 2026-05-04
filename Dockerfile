FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir \
        flask \
        gunicorn \
        scikit-learn \
        xgboost \
        arch \
        pandas \
        plotly \
        openpyxl \
        requests \
        python-dotenv

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app.server:app"]
