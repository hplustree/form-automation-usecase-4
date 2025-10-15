# PostgreSQL Database Integration

## Overview

This project now includes PostgreSQL database integration alongside the existing Redis and Weaviate storage systems. PostgreSQL provides persistent storage for project metadata, document information, and field extraction results with full migration history tracking via Alembic.

## Architecture

### Data Storage Strategy

1. **PostgreSQL** (New)
   - Persistent storage for project metadata
   - Document tracking and status
   - Field extraction results with confidence scores
   - Processing queue management
   - Full migration history with Alembic

2. **Redis** (Existing - Maintained for backward compatibility)
   - Temporary queue management (RQ)
   - Cache for active project data
   - Fast access to processing status

3. **Weaviate** (Existing - Unchanged)
   - Vector storage for document chunks
   - Semantic search capabilities
   - Document embeddings

## Database Schema

### Tables

1. **projects**
   - Project metadata and configuration
   - Status tracking (queued, processing, completed, failed)
   - Field configurations stored as JSON
   - Timestamps for audit trail

2. **documents**
   - Individual document tracking
   - Processing status per document
   - File metadata (size, type, page count)
   - Processing time metrics

3. **field_results**
   - Extraction results for each field
   - Confidence scores and explanations
   - Source page references
   - Model configuration used

4. **processing_queue**
   - FIFO queue management
   - Priority support
   - Worker assignment tracking
   - Retry management

## Features Preserved

All existing functionality has been maintained:

- ✅ Multi-document upload and processing
- ✅ Concurrent field extraction (5 fields in parallel)
- ✅ Sequential document processing
- ✅ Template-based field configuration
- ✅ Real-time status tracking
- ✅ Result retrieval APIs
- ✅ Weaviate vector search
- ✅ Redis queue management
- ✅ Worker scaling (2 workers by default)

## New Features

1. **Persistent Storage**
   - Projects and results persist beyond Redis TTL
   - Historical data retention
   - Audit trail with timestamps

2. **Migration Management**
   - Alembic for schema versioning
   - Easy rollback capabilities
   - Database evolution tracking

3. **Enhanced Querying**
   - Filter projects by status
   - Pagination support
   - SQL-based reporting capabilities

4. **Data Integrity**
   - Foreign key constraints
   - Cascade deletes
   - Transaction support

## Setup Instructions

### 1. Environment Configuration

Add to your `.env` file:
```env
DATABASE_URL=postgresql://postgres:1234@postgres:5432/siso_pipeline
```

### 2. Database Initialization

The database will be automatically initialized when you start the services:

```bash
docker-compose up --build
```

### 3. Manual Migration (if needed)

To run migrations manually:

```bash
# Generate a new migration
docker exec -it siso-pipeline-api alembic revision --autogenerate -m "Your migration message"

# Apply migrations
docker exec -it siso-pipeline-api alembic upgrade head

# Rollback one migration
docker exec -it siso-pipeline-api alembic downgrade -1
```

## API Endpoints

All existing endpoints work as before, now with PostgreSQL backing:

- `POST /project/submit` - Submit new project
- `GET /project/{id}` - Get project status
- `GET /project/{id}/results` - Get extraction results
- `GET /projects` - List all projects (with filtering)
- `DELETE /project/{id}` - Delete project

## Database Access

### PostgreSQL Connection

- **Host**: localhost (from host machine)
- **Port**: 5433
- **Database**: siso_pipeline
- **User**: postgres
- **Password**: 1234

### Connect via psql

```bash
psql -h localhost -p 5433 -U postgres -d siso_pipeline
```

### View Tables

```sql
\dt                    -- List all tables
SELECT * FROM projects;  -- View projects
SELECT * FROM documents; -- View documents
SELECT * FROM field_results; -- View extraction results
```

## Monitoring

### Check Database Status

```bash
# Check if PostgreSQL is running
docker exec siso-pipeline-postgres pg_isready

# View database logs
docker logs siso-pipeline-postgres

# Check table sizes
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline -c "\dt+"
```

### View Migration History

```bash
docker exec -it siso-pipeline-api alembic history
```

## Backup and Restore

### Backup Database

```bash
# Create backup
docker exec siso-pipeline-postgres pg_dump -U postgres siso_pipeline > backup.sql

# With timestamp
docker exec siso-pipeline-postgres pg_dump -U postgres siso_pipeline > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore Database

```bash
# Restore from backup
docker exec -i siso-pipeline-postgres psql -U postgres siso_pipeline < backup.sql
```

## Troubleshooting

### Database Connection Issues

1. Ensure PostgreSQL container is running:
   ```bash
   docker ps | grep postgres
   ```

2. Check PostgreSQL logs:
   ```bash
   docker logs siso-pipeline-postgres
   ```

3. Verify database exists:
   ```bash
   docker exec -it siso-pipeline-postgres psql -U postgres -c "\l"
   ```

### Migration Issues

1. Check current migration version:
   ```bash
   docker exec -it siso-pipeline-api alembic current
   ```

2. Fix migration conflicts:
   ```bash
   docker exec -it siso-pipeline-api alembic stamp head
   ```

## Performance Considerations

1. **Indexes**: Key columns are indexed for optimal query performance
2. **Connection Pooling**: SQLAlchemy configured with connection pooling
3. **Batch Operations**: Field results are batch-inserted for efficiency
4. **Hybrid Storage**: Redis for hot data, PostgreSQL for persistence

## Future Enhancements

Potential improvements that can be added:

1. **Analytics Dashboard**: SQL-based reporting on processing metrics
2. **Data Archival**: Move old projects to archive tables
3. **Advanced Querying**: GraphQL or advanced REST filters
4. **Audit Logging**: Detailed change tracking
5. **Multi-tenancy**: Organization-based data isolation

## Migration from Redis-Only

For existing deployments:

1. Data in Redis remains accessible
2. New projects automatically use PostgreSQL
3. Old projects can be migrated via a script (if needed)
4. No breaking changes to API contracts

## Support

For issues or questions about the database integration:

1. Check logs: `docker-compose logs postgres`
2. Verify migrations: `alembic current`
3. Review this documentation
4. Check DATABASE_INTEGRATION.md for updates
