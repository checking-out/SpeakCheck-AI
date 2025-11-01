from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
from psycopg2 import extensions
from psycopg2.extras import Json, RealDictCursor

from config import Settings


class Database:
    """Lightweight database helper for job orchestration."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._conn: Optional[psycopg2.extensions.connection] = None

    def connect(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed != 0:
            self._conn = psycopg2.connect(self._settings.postgres_dsn, cursor_factory=RealDictCursor)
            self._conn.autocommit = False
        elif self._conn.get_transaction_status() == extensions.TRANSACTION_STATUS_INERROR:
            self._conn.rollback()
        return self._conn

    def close(self) -> None:
        if self._conn and self._conn.closed == 0:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(72) NOT NULL,
                    major VARCHAR(255),
                    age INT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS stages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    stage_name VARCHAR(255) NOT NULL,
                    situation VARCHAR(255),
                    check_list_url VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS speeches (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    stage_id UUID NOT NULL REFERENCES stages(id),
                    title VARCHAR(255) NOT NULL,
                    speech_name VARCHAR(255),
                    video_source TEXT,
                    document_url TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS title VARCHAR(255);")
            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS speech_name VARCHAR(255);")
            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS video_source TEXT;")
            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS document_url TEXT;")
            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
            cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
            cur.execute("ALTER TABLE speeches ALTER COLUMN id SET DEFAULT gen_random_uuid();")
            cur.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'speeches' AND column_name = 'url'
                    ) THEN
                        UPDATE speeches
                        SET video_source = CASE WHEN COALESCE(source_type, 'video') = 'video' THEN url ELSE video_source END,
                            document_url = CASE WHEN COALESCE(source_type, 'video') = 'document' THEN url ELSE document_url END;
                    END IF;
                END;
                $$;
                """
            )
            cur.execute("UPDATE speeches SET created_at = COALESCE(created_at, NOW());")
            cur.execute("UPDATE speeches SET updated_at = COALESCE(updated_at, NOW());")
            cur.execute("ALTER TABLE speeches ALTER COLUMN created_at SET DEFAULT NOW();")
            cur.execute("ALTER TABLE speeches ALTER COLUMN updated_at SET DEFAULT NOW();")
            cur.execute("ALTER TABLE speeches ALTER COLUMN created_at SET NOT NULL;")
            cur.execute("ALTER TABLE speeches ALTER COLUMN updated_at SET NOT NULL;")
            cur.execute(
                """
                UPDATE speeches
                SET title = COALESCE(title, speech_name, 'Untitled Speech')
                WHERE title IS NULL OR title = '';
                """
            )
            cur.execute("ALTER TABLE speeches ALTER COLUMN title SET NOT NULL;")
            cur.execute("ALTER TABLE speeches DROP COLUMN IF EXISTS url;")
            cur.execute("ALTER TABLE speeches DROP COLUMN IF EXISTS source_type;")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS question (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    speech_id UUID NOT NULL REFERENCES speeches(id),
                    question VARCHAR(255) NOT NULL,
                    answer VARCHAR(255),
                    model_answer TEXT,
                    improvement_tips TEXT,
                    user_answer TEXT,
                    ai_feedback TEXT,
                    score INT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                ALTER TABLE question
                    ADD COLUMN IF NOT EXISTS model_answer TEXT,
                    ADD COLUMN IF NOT EXISTS improvement_tips TEXT,
                    ADD COLUMN IF NOT EXISTS user_answer TEXT,
                    ADD COLUMN IF NOT EXISTS ai_feedback TEXT,
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    id SERIAL PRIMARY KEY,
                    video_source TEXT NOT NULL,
                    user_id UUID,
                    stage_id UUID,
                    speech_id UUID,
                    language VARCHAR(16) DEFAULT 'ko',
                    model_size VARCHAR(16) DEFAULT 'medium',
                    generate_questions BOOLEAN DEFAULT TRUE,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    transcript TEXT,
                    transcript_metadata JSONB,
                    questions JSONB,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute("ALTER TABLE transcription_jobs ADD COLUMN IF NOT EXISTS user_id UUID;")
            cur.execute("ALTER TABLE transcription_jobs ADD COLUMN IF NOT EXISTS stage_id UUID;")
            cur.execute("ALTER TABLE transcription_jobs ADD COLUMN IF NOT EXISTS speech_id UUID;")
            cur.execute("ALTER TABLE transcription_jobs ALTER COLUMN language SET DEFAULT 'ko';")
            cur.execute("ALTER TABLE transcription_jobs ALTER COLUMN model_size SET DEFAULT 'medium';")
            cur.execute("ALTER TABLE transcription_jobs ALTER COLUMN generate_questions SET DEFAULT TRUE;")

            cur.execute(
                """
                UPDATE transcription_jobs
                SET language = 'ko'
                WHERE language IS DISTINCT FROM 'ko';
                """
            )
            cur.execute(
                """
                UPDATE transcription_jobs
                SET model_size = 'medium'
                WHERE model_size IS DISTINCT FROM 'medium';
                """
            )
            cur.execute(
                """
                UPDATE transcription_jobs
                SET generate_questions = TRUE
                WHERE generate_questions IS DISTINCT FROM TRUE;
                """
            )

            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.table_constraints
                        WHERE constraint_name = 'transcription_jobs_user_id_fkey'
                    ) THEN
                        ALTER TABLE transcription_jobs
                        ADD CONSTRAINT transcription_jobs_user_id_fkey
                        FOREIGN KEY (user_id) REFERENCES users(id);
                    END IF;
                END;
                $$;
                """
            )

            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.table_constraints
                        WHERE constraint_name = 'transcription_jobs_stage_id_fkey'
                    ) THEN
                        ALTER TABLE transcription_jobs
                        ADD CONSTRAINT transcription_jobs_stage_id_fkey
                        FOREIGN KEY (stage_id) REFERENCES stages(id);
                    END IF;
                END;
                $$;
                """
            )

            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.table_constraints
                        WHERE constraint_name = 'transcription_jobs_speech_id_fkey'
                    ) THEN
                        ALTER TABLE transcription_jobs
                        ADD CONSTRAINT transcription_jobs_speech_id_fkey
                        FOREIGN KEY (speech_id) REFERENCES speeches(id);
                    END IF;
                END;
                $$;
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcription_jobs_status
                ON transcription_jobs (status);
                """
            )
            conn.commit()

    def fetch_next_job(self) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,
                       video_source,
                       COALESCE(language, 'ko') AS language,
                       COALESCE(model_size, 'medium') AS model_size,
                       COALESCE(generate_questions, TRUE) AS generate_questions,
                       user_id,
                       stage_id,
                       speech_id
                FROM transcription_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1;
                """
            )
            job = cur.fetchone()
            if job:
                cur.execute(
                    """
                    UPDATE transcription_jobs
                    SET status = 'processing',
                        updated_at = NOW(),
                        error_message = NULL
                    WHERE id = %s;
                    """,
                    (job["id"],),
                )
                conn.commit()
            else:
                conn.rollback()
            return job

    def create_job(
        self,
        *,
        video_source: str,
        user_id: UUID,
        stage_id: UUID,
        speech_id: UUID,
    ) -> Dict[str, Any]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transcription_jobs (
                    video_source,
                    user_id,
                    stage_id,
                    speech_id,
                    status
                )
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING *;
                """,
                (video_source, str(user_id), str(stage_id), str(speech_id)),
            )
            job = cur.fetchone()
            conn.commit()
            return job

    def get_stage(self, stage_id: UUID) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM stages
                WHERE id = %s;
                """,
                (str(stage_id),),
            )
            stage = cur.fetchone()
            conn.commit()
            return stage

    def list_speeches_for_stage(self, stage_id: UUID) -> List[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM speeches
                WHERE stage_id = %s
                ORDER BY created_at ASC;
                """,
                (str(stage_id),),
            )
            speeches = cur.fetchall()
            conn.commit()
            return speeches

    def get_speech(self, speech_id: UUID) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM speeches
                WHERE id = %s;
                """,
                (str(speech_id),),
            )
            speech = cur.fetchone()
            conn.commit()
            return speech

    def delete_speech(self, speech_id: UUID) -> None:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM question
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.execute(
                """
                DELETE FROM transcription_jobs
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.execute(
                """
                DELETE FROM speeches
                WHERE id = %s;
                """,
                (str(speech_id),),
            )
            conn.commit()

    def create_speech(
        self,
        *,
        stage_id: UUID,
        title: str,
        video_source: Optional[str] = None,
        document_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO speeches (
                    stage_id,
                    title,
                    speech_name,
                    video_source,
                    document_url
                )
                VALUES (%s, %s, NULL, %s, %s)
                RETURNING *;
                """,
                (str(stage_id), title, video_source, document_url),
            )
            speech = cur.fetchone()
            conn.commit()
            return speech

    def update_speech_video(
        self,
        *,
        speech_id: UUID,
        title: str,
        video_source: str,
    ) -> Dict[str, Any]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM question
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.execute(
                """
                UPDATE transcription_jobs
                SET status = 'cancelled',
                    updated_at = NOW()
                WHERE speech_id = %s AND status IN ('pending', 'processing');
                """,
                (str(speech_id),),
            )
            cur.execute(
                """
                UPDATE speeches
                SET title = %s,
                    video_source = %s,
                    speech_name = NULL,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (title, video_source, str(speech_id)),
            )
            updated = cur.fetchone()
            conn.commit()
            return updated

    def update_speech_document(
        self,
        *,
        speech_id: UUID,
        title: str,
        document_url: str,
    ) -> Dict[str, Any]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM question
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.execute(
                """
                UPDATE speeches
                SET title = %s,
                    document_url = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (title, document_url, str(speech_id)),
            )
            updated = cur.fetchone()
            conn.commit()
            return updated

    def update_speech_after_transcription(
        self,
        speech_id: UUID,
        transcript: str,
        document_text: Optional[str] = None,
    ) -> None:
        combined = "\n\n".join(
            part.strip()
            for part in [transcript or "", document_text or ""]
            if part and part.strip()
        )

        snippet = combined.strip() if combined else (transcript or "").strip()
        snippet = snippet[:255] if snippet else None

        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE speeches
                SET speech_name = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (snippet, str(speech_id)),
            )
            conn.commit()

    def store_questions(self, speech_id: UUID, questions: List[Dict[str, Any]]) -> None:
        if not questions:
            return

        payload = [
            (
                str(speech_id),
                question.get("question"),
                question.get("answer"),
                question.get("model_answer"),
                question.get("improvement_tips"),
                None,
                None,
                question.get("score"),
            )
            for question in questions
            if question.get("question")
        ]

        if not payload:
            return

        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM question
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.executemany(
                """
                INSERT INTO question (
                    speech_id,
                    question,
                    answer,
                    model_answer,
                    improvement_tips,
                    user_answer,
                    ai_feedback,
                    score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                payload,
            )
            conn.commit()

    def upsert_questions(self, speech_id: UUID, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not questions:
            return []

        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM question
                WHERE speech_id = %s;
                """,
                (str(speech_id),),
            )
            cur.executemany(
                """
                INSERT INTO question (
                    speech_id,
                    question,
                    answer,
                    model_answer,
                    improvement_tips,
                    user_answer,
                    ai_feedback,
                    score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                [
                    (
                        str(speech_id),
                        q.get("question"),
                        q.get("answer"),
                        q.get("model_answer"),
                        q.get("improvement_tips"),
                        None,
                        None,
                        q.get("score"),
                    )
                    for q in questions
                    if q.get("question")
                ],
            )
            cur.execute(
                """
                SELECT *
                FROM question
                WHERE speech_id = %s
                ORDER BY created_at ASC;
                """,
                (str(speech_id),),
            )
            saved_questions = cur.fetchall()
            conn.commit()
            return saved_questions

    def list_questions_for_speech(self, speech_id: UUID) -> List[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM question
                WHERE speech_id = %s
                ORDER BY created_at ASC;
                """,
                (str(speech_id),),
            )
            questions = cur.fetchall()
            conn.commit()
            return questions

    def get_question(self, question_id: UUID) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM question
                WHERE id = %s;
                """,
                (str(question_id),),
            )
            question = cur.fetchone()
            conn.commit()
            return question

    def update_question_feedback(
        self,
        question_id: UUID,
        *,
        user_answer: str,
        ai_feedback: str,
        score: Optional[int] = None,
    ) -> None:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE question
                SET user_answer = %s,
                    ai_feedback = %s,
                    score = COALESCE(%s, score),
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (user_answer, ai_feedback, score, str(question_id)),
            )
            conn.commit()

    def get_latest_completed_job_for_speech(self, speech_id: UUID) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM transcription_jobs
                WHERE speech_id = %s AND status = 'completed'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1;
                """,
                (str(speech_id),),
            )
            job = cur.fetchone()
            conn.commit()
            return job

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM transcription_jobs
                WHERE id = %s;
                """,
                (job_id,),
            )
            job = cur.fetchone()
            conn.commit()
            return job

    def list_jobs(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM transcription_jobs
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            jobs = cur.fetchall()
            conn.commit()
            return jobs

    def mark_completed(
        self,
        job_id: int,
        transcript: str,
        quality_info: Dict[str, Any],
        questions: Optional[Any] = None,
    ) -> None:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transcription_jobs
                SET status = 'completed',
                    transcript = %s,
                    transcript_metadata = %s,
                    questions = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (
                    transcript,
                    Json(quality_info),
                    Json(questions) if questions is not None else None,
                    job_id,
                ),
            )
            conn.commit()

    def mark_failed(self, job_id: int, error_message: str) -> None:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transcription_jobs
                SET status = 'failed',
                    error_message = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (error_message[:2000], job_id),
            )
            conn.commit()
