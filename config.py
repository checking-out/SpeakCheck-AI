import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    jwt_secret_key: str
    aws_access_key: str
    aws_secret_key: str
    aws_region: str
    aws_bucket: str
    downloads_dir: str = "downloads"
    audio_output_dir: str = "audio"
    job_batch_size: int = 1

    @staticmethod
    def from_env() -> "Settings":
        """Load environment configuration with sensible defaults."""
        load_dotenv()

        env = os.getenv

        postgres_db = env("POSTGRES_DB")
        postgres_user = env("POSTGRES_USER")
        postgres_password = env("POSTGRES_PASSWORD")
        jwt_secret_key = env("JWT_SECRET_KEY")
        aws_access_key = env("AWS_ACCESS_KEY")
        aws_secret_key = env("AWS_SECRET_KEY")

        missing = [
            name
            for name, value in [
                ("POSTGRES_DB", postgres_db),
                ("POSTGRES_USER", postgres_user),
                ("POSTGRES_PASSWORD", postgres_password),
                ("JWT_SECRET_KEY", jwt_secret_key),
                ("AWS_ACCESS_KEY", aws_access_key),
                ("AWS_SECRET_KEY", aws_secret_key),
            ]
            if not value
        ]

        if missing:
            missing_vars = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variables: {missing_vars}")

        postgres_host = env("POSTGRES_HOST", "localhost")
        postgres_port = int(env("POSTGRES_PORT", "5432"))
        aws_region = env("AWS_REGION", env("AWS_DEFAULT_REGION", "ap-northeast-2"))
        aws_bucket = env("AWS_BUCKET")
        if not aws_bucket:
            raise RuntimeError("Missing required environment variable: AWS_BUCKET")

        downloads_dir = env("DOWNLOADS_DIR", "downloads")
        audio_output_dir = env("AUDIO_OUTPUT_DIR", "audio")
        job_batch_size = int(env("JOB_BATCH_SIZE", "1"))

        return Settings(
            postgres_db=postgres_db,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            jwt_secret_key=jwt_secret_key,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            aws_region=aws_region,
            aws_bucket=aws_bucket,
            downloads_dir=downloads_dir,
            audio_output_dir=audio_output_dir,
            job_batch_size=job_batch_size,
        )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
