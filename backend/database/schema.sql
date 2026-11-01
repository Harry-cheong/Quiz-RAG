-- question table
CREATE TABLE IF NOT EXISTS questions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty TEXT NOT NULL
);

-- child table for attempts
CREATE TABLE IF NOT EXISTS attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    proficiency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- index for search by name
CREATE INDEX IF NOT EXISTS idx_name
    ON questions (name);

-- index for search by topic
CREATE INDEX IF NOT EXISTS idx_topic
    ON questions (topic);

-- index for search by difficulty
CREATE INDEX IF NOT EXISTS idx_difficulty
    ON questions (difficulty);

-- index for finding all the attempts for the selected question
CREATE INDEX IF NOT EXISTS idx_question_id
    ON attempts (question_id);