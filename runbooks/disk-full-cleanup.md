# Runbook: Disk full on an application host

**Scope:** Linux hosts running Docker workloads; Windows hosts running IIS and SQL Server.  
**Severity guidance:** P1 if the database host is at 100% (writes fail); P2 if an application host is above 95%; P3 above 85%.

## Linux hosts
1. Find what is full: `df -h` then `sudo du -xh --max-depth=1 / | sort -h | tail -15`.
2. The usual suspects, in order:
   - **Docker**: `docker system df`. Reclaim with `docker image prune -a --filter "until=168h"` (images older than 7 days) and `docker builder prune`. Never run `docker system prune --volumes` on a host with databases; it deletes unused named volumes.
   - **Container logs**: `sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail`. Truncate a huge log with `sudo truncate -s 0 <file>` and add log rotation in `/etc/docker/daemon.json`: `"log-opts": {"max-size": "50m", "max-file": "3"}` (needs a Docker restart to apply to new containers).
   - **journald**: `sudo journalctl --vacuum-size=500M`.
   - **Old backups / dumps** in `/opt/backups` or `/tmp`: move to object storage before deleting.
3. Confirm free space is back above 20% with `df -h`.
4. If the host is a VM with a resizable disk, grow it (cloud console or hypervisor) and then `sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1` (or `xfs_growfs /` for XFS).

## Windows hosts
1. Identify the large folders with `Get-ChildItem C:\ -Directory | ForEach-Object { [pscustomobject]@{ Dir=$_.FullName; GB=[math]::Round((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1GB,1) } } | Sort-Object GB -Descending | Select-Object -First 10`.
2. Usual suspects: IIS logs (`C:\inetpub\logs\LogFiles`), SQL Server backup folder, Windows Update cache (`cleanmgr`), old TeamCity / build agent work directories.
3. For SQL Server transaction logs growing without bound, check the recovery model and take a log backup before shrinking; do not shrink the data file.

## Prevent repeat incidents
- Disk usage alert at 80% and 90% on every host.
- Log rotation for Docker and IIS configured by the provisioning script, not by hand.
- Backups written to object storage with a lifecycle rule, not to the local disk.
