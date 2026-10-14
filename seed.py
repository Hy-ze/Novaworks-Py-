"""Creates the 10 demo users. Safe to re-run (upsert by id)."""
import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()
USERS = [
    ("ADMIN", "Admin", "admin@novaworks.example", "ADMIN", "Administrator", "Company overview, transcript creation"),
    ("PM01", "Ayesha Khan", "ayesha@novaworks.example", "MANAGER", "Web PM", "Web projects, client coordination"),
    ("PM02", "Bilal Ahmed", "bilal@novaworks.example", "MANAGER", "Mobile PM", "Mobile projects, delivery planning"),
    ("PM03", "Hina Malik", "hina@novaworks.example", "MANAGER", "AI PM", "AI projects, requirement review"),
    ("DEV01", "Ali Raza", "ali@novaworks.example", "AGENT", "Full-Stack Developer", "React, frontend integration"),
    ("DEV02", "Hamza Shah", "hamza@novaworks.example", "AGENT", "Full-Stack Developer", "Node.js, databases, APIs"),
    ("DEV03", "Sara Noor", "sara@novaworks.example", "AGENT", "App Developer", "Flutter, mobile UI"),
    ("DEV04", "Usman Tariq", "usman@novaworks.example", "AGENT", "App Developer", "Flutter, integration, testing"),
    ("DEV05", "Zain Abbas", "zain@novaworks.example", "AGENT", "AI Developer", "LLMs, extraction, prompts"),
    ("DEV06", "Maryam Asif", "maryam@novaworks.example", "AGENT", "AI Developer", "Retrieval, document processing"),
]

conn = pymysql.connect(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3306")),
                       user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
                       database=os.getenv("DB_NAME", "novaworks"))
with conn.cursor() as c:
    for uid, name, email, role, spec, skills in USERS:
        c.execute(
            """INSERT INTO users (id,name,email,password_hash,role,specialization,skills)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email), password_hash=VALUES(password_hash),
               role=VALUES(role), specialization=VALUES(specialization), skills=VALUES(skills)""",
            (uid, name, email, generate_password_hash("Demo123!"), role, spec, skills))
conn.commit()
conn.close()
print(f"Seeded {len(USERS)} users.")
