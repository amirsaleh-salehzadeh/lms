# OpenEduCat database backup

Captured on 2026-10-25 from the running `openeducat` PostgreSQL database and its matching Odoo filestore.

- `openeducat_20261025.dump`: PostgreSQL custom-format dump.
- `openeducat_filestore_20261025.tar.gz`: Odoo attachments and files for the same database.

## Restore on the Ubuntu server

Run these commands from the project directory. They restore the database into the Compose PostgreSQL service and the files into Odoo's persistent data volume.

```sh
docker compose up -d db
docker compose exec -T db createdb -U odoo -O odoo openeducat
docker compose exec -T db pg_restore -U odoo -d openeducat --no-owner --no-acl < backups/openeducat_20261025.dump
docker compose up -d odoo
docker compose cp backups/openeducat_filestore_20261025.tar.gz odoo:/tmp/openeducat_filestore.tar.gz
docker compose exec -T odoo sh -lc 'mkdir -p /var/lib/odoo/filestore && tar -xzf /tmp/openeducat_filestore.tar.gz -C /var/lib/odoo/filestore && chown -R odoo:odoo /var/lib/odoo/filestore/openeducat'
```

The destination database must not already exist. The dump and filestore must be restored as a matching pair.
