# Deployment Guide - PostgreSQL Integration

## Quick Start

### 1. Stop Existing Services (if running)
```bash
docker-compose down -v
```

### 2. Clean Build and Start
```bash
# Build fresh images
docker-compose build --no-cache

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

### 3. Verify Services
```bash
# Check all containers are running
docker ps

# Expected output should show:
# - siso-pipeline-api
# - siso-pipeline-workers
# - siso-pipeline-postgres
# - siso-pipeline-redis
# - siso-pipeline-weaviate
# - siso-pipeline-litellm
```

### 4. Test Database Connection
```bash
# Test from host machine
psql -h localhost -p 5433 -U postgres -d siso_pipeline -c "SELECT 1;"

# Test from API container
docker exec -it siso-pipeline-api python test_postgres_integration.py
```

### 5. Test API Endpoints
```bash
# Health check
curl http://localhost:8001/health

# List projects (should be empty initially)
curl http://localhost:8001/projects
```

## Step-by-Step Testing

### Test 1: Submit a Project
```bash
# Create a test PDF file
echo "Test document content" > test.txt
# Convert to PDF (requires libreoffice)
libreoffice --headless --convert-to pdf test.txt

# Submit project via API
curl -X POST "http://localhost:8001/project/submit" \
  -F "project_name=Test Project" \
  -F 'field_names=["effective_date", "company"]' \
  -F "template_name=spa_fields" \
  -F "files=@test.pdf"

# Save the project_id from response
```

### Test 2: Check Project Status
```bash
# Replace PROJECT_ID with actual ID from previous step
curl http://localhost:8001/project/{PROJECT_ID}
```

### Test 3: Verify Database Records
```bash
# Connect to PostgreSQL
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline

# In psql prompt:
\dt                          # List all tables
SELECT * FROM projects;      # View projects
SELECT * FROM documents;     # View documents
SELECT * FROM processing_queue; # View queue
\q                          # Exit
```

### Test 4: Check Logs
```bash
# API logs
docker logs siso-pipeline-api -f

# Worker logs
docker logs siso-pipeline-workers -f

# PostgreSQL logs
docker logs siso-pipeline-postgres
```

## Verification Checklist

### ✅ Database Setup
- [ ] PostgreSQL container is running
- [ ] Database `siso_pipeline` exists
- [ ] All tables are created (projects, documents, field_results, processing_queue)
- [ ] Can connect from host machine on port 5433

### ✅ Application Integration
- [ ] API starts without errors
- [ ] Workers start without errors
- [ ] Database initialization completes
- [ ] Health check endpoint returns healthy

### ✅ Functionality Tests
- [ ] Can submit a new project
- [ ] Project appears in PostgreSQL
- [ ] Project status updates correctly
- [ ] Field extraction results are stored
- [ ] Can retrieve project results
- [ ] Can list all projects
- [ ] Can delete a project

## Common Issues and Solutions

### Issue 1: Database Connection Failed
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check PostgreSQL logs
docker logs siso-pipeline-postgres

# Verify database exists
docker exec -it siso-pipeline-postgres psql -U postgres -c "\l"

# Recreate database if needed
docker exec -it siso-pipeline-postgres psql -U postgres -c "CREATE DATABASE siso_pipeline;"
```

### Issue 2: Migration Errors
```bash
# Check current migration status
docker exec -it siso-pipeline-api alembic current

# Generate new migration
docker exec -it siso-pipeline-api alembic revision --autogenerate -m "Initial migration"

# Apply migrations
docker exec -it siso-pipeline-api alembic upgrade head

# If stuck, stamp head
docker exec -it siso-pipeline-api alembic stamp head
```

### Issue 3: Permission Errors
```bash
# Fix file permissions
chmod +x entrypoint.sh
chmod +x run_migrations.sh
chmod +x init_db.py
```

### Issue 4: Port Conflicts
```bash
# Check if ports are in use
netstat -tulpn | grep -E '8001|5433|6380|8085|4000'

# Stop conflicting services or change ports in docker-compose.yml
```

## Monitoring Commands

### Database Monitoring
```bash
# Connection count
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline -c "SELECT count(*) FROM pg_stat_activity;"

# Table sizes
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline -c "\dt+"

# Active queries
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline -c "SELECT pid, query, state FROM pg_stat_activity WHERE state != 'idle';"
```

### Application Monitoring
```bash
# API logs with timestamp
docker logs -f --timestamps siso-pipeline-api

# Worker activity
docker logs -f siso-pipeline-workers | grep "Processing"

# Redis queue length
docker exec -it siso-pipeline-redis redis-cli LLEN rq:queue:projects
```

## Production Deployment

### Environment Variables
Create `.env` file from template:
```bash
cp .env.example .env
```

Edit `.env` and set:
```env
# Required
LITELLM_MASTER_KEY=your_actual_key
DATABASE_URL=postgresql://postgres:1234@postgres:5432/siso_pipeline

# Optional - adjust for production
REDIS_TTL_SECONDS=2592000  # 30 days
MAX_CONCURRENT_FIELDS=10   # Increase for more parallelism
NUM_WORKERS=4               # Increase workers for more throughput
```

### Docker Compose Production
```bash
# Start in detached mode
docker-compose up -d

# Scale workers
docker-compose up -d --scale workers=4

# View resource usage
docker stats
```

### Backup Strategy
```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backups/postgres"
mkdir -p $BACKUP_DIR
docker exec siso-pipeline-postgres pg_dump -U postgres siso_pipeline | gzip > $BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

## Rollback Procedure

If issues occur after deployment:

### 1. Quick Rollback
```bash
# Stop services
docker-compose down

# Restore previous version
git checkout previous-version

# Rebuild and start
docker-compose build
docker-compose up -d
```

### 2. Database Rollback
```bash
# Rollback last migration
docker exec -it siso-pipeline-api alembic downgrade -1

# Or rollback to specific revision
docker exec -it siso-pipeline-api alembic downgrade <revision_id>
```

### 3. Data Recovery
```bash
# Restore from backup
gunzip < backup_20241015.sql.gz | docker exec -i siso-pipeline-postgres psql -U postgres siso_pipeline
```

## Performance Tuning

### PostgreSQL Optimization
Add to `docker-compose.yml` under postgres service:
```yaml
command:
  - "postgres"
  - "-c"
  - "max_connections=200"
  - "-c"
  - "shared_buffers=256MB"
  - "-c"
  - "effective_cache_size=1GB"
  - "-c"
  - "maintenance_work_mem=64MB"
```

### Connection Pooling
Already configured in `app/db/database.py`:
- pool_size=10
- max_overflow=20

## Success Indicators

Your integration is working correctly when:

1. ✅ All containers start without errors
2. ✅ Health check returns all services as "healthy"
3. ✅ Projects persist after container restart
4. ✅ Can query historical data from PostgreSQL
5. ✅ Migrations run successfully
6. ✅ No data loss during processing
7. ✅ Performance remains consistent

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Review `DATABASE_INTEGRATION.md`
3. Run test script: `python test_postgres_integration.py`
4. Check database: `psql -h localhost -p 5433 -U postgres -d siso_pipeline`
