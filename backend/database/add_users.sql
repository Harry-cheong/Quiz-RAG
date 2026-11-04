ALTER TABLE attempts
    ADD COLUMN user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;

UPDATE attempts as a
SET user_id = 1
WHERE user_id IS NULL;

ALTER TABLE attempts
    ALTER COLUMN user_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_attempts_user_question
    ON attempts (user_id, question_id);

COMMIT