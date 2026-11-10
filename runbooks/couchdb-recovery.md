# Runbook: CouchDB crash recovery

**Service:** CouchDB 2.x cluster (3 nodes)  
**Owner:** Platform team  
**Severity guidance:** P1 if all nodes are down or writes fail; P2 if a single node is out and replication is lagging.

## Symptoms
- `curl http://<node>:5984/_up` returns connection refused or `{"status":"maintenance_mode"}`.
- Application logs show `nodedown` or `timeout` errors from the CouchDB client.
- After a host reboot the `couchdb` service is in a crash loop (`systemctl status couchdb` shows `activating (auto-restart)`).

## Most common root cause
The data disk did not mount before CouchDB started, so the service failed on an empty or missing data directory. On our hosts the data volume is `/media/store` (NVMe device `nvme2n1`).

## Recovery steps
1. **Stop the crash loop first** so the node does not keep restarting on a bad disk:
   `sudo systemctl stop couchdb`
2. **Check the data disk is mounted:**
   `df -h /media/store` and `lsblk`. If `/media/store` is not a mount point, mount it:
   `sudo mount /dev/nvme2n1 /media/store`
3. **Make the mount survive reboots.** Confirm there is an `/etc/fstab` line for the volume using its UUID (`sudo blkid /dev/nvme2n1`), for example:
   `UUID=<uuid>  /media/store  ext4  defaults,nofail  0 2`
   The `nofail` option prevents the host from hanging at boot if the disk is missing.
4. **Add a systemd dependency** so CouchDB waits for the mount:
   `sudo systemctl edit couchdb` and add `RequiresMountsFor=/media/store` under `[Unit]`, then `sudo systemctl daemon-reload`.
5. **Start CouchDB and verify:**
   `sudo systemctl start couchdb`, then `curl -s http://localhost:5984/_up` should return `{"status":"ok"}`.
6. **Check cluster membership and replication:**
   `curl -s http://admin:<pw>@localhost:5984/_membership` must list all three nodes under `cluster_nodes` and `all_nodes`.
   `curl -s http://admin:<pw>@localhost:5984/_scheduler/jobs` shows replication jobs; a job stuck in `crashing` state means the target node is still unreachable.
7. **Re-run the application smoke test** (login + one document read) before closing the incident.

## If the data directory is genuinely lost
Do **not** start CouchDB on an empty directory in a cluster; it will join as a fresh node and the other nodes will start full replication, which can saturate the network. Restore the latest snapshot of the data volume first, then follow steps 4-7.

## Post-incident
- Open a P2 ticket to track the fstab/systemd hardening on every CouchDB host.
- Record the timeline (first alert, mitigation, recovery) in the incident document.
