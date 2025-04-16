# 🐘 Using pgAdmin to Manage PostgreSQL in Docker

This guide explains how to use **pgAdmin (running in Docker)** to connect to and monitor a **PostgreSQL database (also running in Docker)**.

---

## ✅ Step 1: Access pgAdmin in Browser

Open your browser and go to:

```
http://localhost:5050
```

> Or replace `5050` with the port you mapped in `docker-compose.yml`.

### 🔐 Login Credentials
Use the credentials defined in your `docker-compose.yml`:

```
Email:    admin@uwi.com
Password: admin123
```

---

## ✅ Step 2: Register the Postgres Server

If you haven’t already:

1. In the pgAdmin sidebar, right-click **Servers → Create → Server**
2. Fill in the fields below:

### 🔧 General Tab
- **Name:** `UWI DB` (or any name you like)

### 🧠 Connection Tab
| Field          | Value          |
|----------------|----------------|
| Hostname       | `postgres`     |
| Port           | `5432`         |
| Username       | `user_api`     |
| Password       | `secret`       |
| Maintenance DB | `user_db`      |

☑️ Check "Save Password"

> 🔁 Use `postgres` as the hostname **because pgAdmin and Postgres are in the same Docker network** defined by Docker Compose.

3. Click **Save**.

---

## ✅ Done!

You are now connected to your PostgreSQL database running in Docker via pgAdmin. You can:

- 🧩 Browse tables and schemas
- 🧪 Run SQL queries
- 📊 Monitor connections and server activity
- 📁 Export and import data

Let me know if you want steps for auto-generating ER diagrams or performing backups from pgAdmin!