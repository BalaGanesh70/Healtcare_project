# Multi-Database Setup Guide for Healthcare Platform

This guide will help you set up PostgreSQL, MySQL, and SQLite databases for your healthcare platform. All three databases will work simultaneously, ensuring data consistency across platforms.

## 🗄️ Database Overview

- **PostgreSQL**: Primary database (required)
- **MySQL**: Secondary database (optional)
- **SQLite**: Local database file (optional)

## 📋 Prerequisites

- Windows 10/11
- Python 3.8+
- Administrator privileges for database installation

## 🚀 Installation Steps

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install PostgreSQL

1. **Download PostgreSQL**: Go to [PostgreSQL Downloads](https://www.postgresql.org/download/windows/)
2. **Download the installer** for Windows x86-64
3. **Run the installer**:
   - Choose installation directory
   - Set password for `postgres` user
   - Keep default port (5432)
   - Install all components
4. **Create database**:
   ```sql
   -- Open pgAdmin or psql
   CREATE DATABASE healthcare_data;
   CREATE USER your_username WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE healthcare_data TO your_username;
   ```

### 3. Install MySQL

1. **Download MySQL**: Go to [MySQL Downloads](https://dev.mysql.com/downloads/mysql/)
2. **Download MySQL Community Server** for Windows
3. **Run the installer**:
   - Choose "Developer Default" or "Server only"
   - Set root password
   - Keep default port (3306)
   - Complete installation
4. **Create database**:
   ```sql
   -- Open MySQL Workbench or mysql command line
   CREATE DATABASE healthcare_data;
   CREATE USER 'Bala'@'localhost' IDENTIFIED BY '9788';
   GRANT ALL PRIVILEGES ON healthcare_data.* TO 'Bala'@'localhost';
   FLUSH PRIVILEGES;
   ```

### 4. Configure SQLite

SQLite is included with Python and requires no installation. The database file will be created automatically in the `backend` directory.

### 5. Environment Configuration

1. **Copy the template**:
   ```bash
   copy backend\env_template.txt backend\.env
   ```

2. **Edit `.env` file** with your database credentials:
   ```env
   # PostgreSQL (Required)
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=healthcare_data
   POSTGRES_USER=your_postgres_username
   POSTGRES_PASSWORD=your_postgres_password

   # MySQL (Optional)
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_DB=healthcare_data
   MYSQL_USER=your_mysql_username
   MYSQL_PASSWORD=your_mysql_password

   # SQLite (Optional)
   SQLITE_PATH=healthcare_data.db

   # OpenAI API Key
   OPENAI_API_KEY=your_openai_api_key_here
   ```

## 🔧 Testing the Setup

### 1. Test Database Connections

```bash
cd backend
python -c "
from multi_db_config import test_all_connections
print('Testing database connections...')
status = test_all_connections()
print(f'Connection status: {status}')
"
```

### 2. Start the Application

```bash
cd backend
python main.py
```

### 3. Check Database Status

Visit: `http://localhost:8000/db-status`

Expected response:
```json
{
  "multi_db_enabled": true,
  "connection_status": {
    "postgresql": true,
    "mysql": true,
    "sqlite": true
  },
  "schemas_by_database": {
    "postgresql": [],
    "mysql": [],
    "sqlite": []
  }
}
```

## 📊 How It Works

### Data Synchronization

1. **Schema Creation**: When you create a schema, it's created in all three databases
2. **Table Creation**: Tables are created with appropriate syntax for each database
3. **Data Insertion**: Data is inserted simultaneously into all databases
4. **Updates**: Protection updates are applied to all databases
5. **Deletions**: Schema withdrawals remove data from all databases

### Database-Specific Features

- **PostgreSQL**: Full schema support, JSONB for audit trails
- **MySQL**: Full schema support, JSON for audit trails
- **SQLite**: Table prefixes (no schema support), TEXT for audit trails

## 🚨 Troubleshooting

### Common Issues

1. **PostgreSQL Connection Failed**
   - Check if PostgreSQL service is running
   - Verify credentials in `.env` file
   - Ensure database exists

2. **MySQL Connection Failed**
   - Check if MySQL service is running
   - Verify credentials in `.env` file
   - Ensure database exists

3. **SQLite Permission Error**
   - Check write permissions in backend directory
   - Ensure disk space is available

### Service Management

**PostgreSQL**:
```bash
# Start service
net start postgresql-x64-15

# Stop service
net stop postgresql-x64-15
```

**MySQL**:
```bash
# Start service
net start MySQL80

# Stop service
net stop MySQL80
```

## 🔒 Security Considerations

1. **Strong Passwords**: Use strong, unique passwords for each database
2. **Network Security**: Keep databases on localhost for development
3. **Environment Variables**: Never commit `.env` files to version control
4. **Database Users**: Use dedicated users with minimal required privileges

## 📈 Performance Notes

- **PostgreSQL**: Best for complex queries and large datasets
- **MySQL**: Good for read-heavy workloads
- **SQLite**: Excellent for local development and testing
- **Synchronization**: All operations are performed sequentially to ensure consistency

## 🆘 Support

If you encounter issues:

1. Check the application logs for detailed error messages
2. Verify all database services are running
3. Test individual database connections
4. Ensure all environment variables are set correctly

## 🔄 Migration from Single Database

If you're upgrading from the single-database version:

1. Your existing PostgreSQL data will be preserved
2. New operations will automatically sync to all databases
3. The system maintains backward compatibility
4. You can disable multi-database mode by removing MySQL/SQLite credentials

---

**Note**: This setup ensures that all your healthcare data operations are automatically synchronized across three different database systems, providing redundancy and flexibility for different deployment scenarios.
