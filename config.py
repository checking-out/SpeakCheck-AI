import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    postgres_url: str
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
        load_dotenv()
        env = os.getenv

        postgres_url = env("POSTGRES_URL")
        jwt_secret_key = env("JWT_SECRET_KEY")
        aws_access_key = env("AWS_ACCESS_KEY")
        aws_secret_key = env("AWS_SECRET_KEY")

        missing = [
            name
            for name, value in [
                ("POSTGRES_URL", postgres_url),
                ("JWT_SECRET_KEY", jwt_secret_key),
                ("AWS_ACCESS_KEY", aws_access_key),
                ("AWS_SECRET_KEY", aws_secret_key),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        aws_region = env("AWS_REGION", env("AWS_DEFAULT_REGION", "ap-northeast-2"))
        aws_bucket = env("AWS_BUCKET")
        if not aws_bucket:
            raise RuntimeError("Missing required environment variable: AWS_BUCKET")

        downloads_dir = env("DOWNLOADS_DIR", "downloads")
        audio_output_dir = env("AUDIO_OUTPUT_DIR", "audio")
        job_batch_size = int(env("JOB_BATCH_SIZE", "1"))

        return Settings(
            postgres_url=postgres_url,
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
        return self.postgres_url
