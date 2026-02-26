FROM registry.access.redhat.com/ubi9/python-311:latest

LABEL name="pipeclear" \
      version="0.2.0" \
      summary="Pre-flight validation for Jupyter notebooks on RHOAI" \
      maintainer="Ugo Giordano"

WORKDIR /app

COPY pyproject.toml .
COPY pipeclear/ pipeclear/

RUN pip install --no-cache-dir .

ENTRYPOINT ["pipeclear"]
CMD ["--help"]
