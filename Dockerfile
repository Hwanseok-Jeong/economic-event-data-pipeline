FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MPLCONFIGDIR=/tmp/matplotlib HOME=/home/pipeline
WORKDIR /app
COPY requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && useradd --create-home --uid 10001 pipeline
COPY pipeline.py database.py study.py dashboard.py surprise_analysis.py \
     build_case_report.py build_real_report.py build_portfolio.py fetch_cash_prices.py \
     container_runner.py docker_smoke.py ./
COPY sql/ ./sql/
COPY tests/ ./tests/
COPY results/ ./results/
COPY docs/presentation_public.pdf docs/presentation_synthetic.pdf ./docs/
RUN mkdir -p outputs data && chown -R pipeline:pipeline /app
USER pipeline
EXPOSE 8501
CMD ["python", "container_runner.py", "dashboard"]
