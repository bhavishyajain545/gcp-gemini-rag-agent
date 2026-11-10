# Runbook: TLS certificate renewal and expiry incidents

**Scope:** Public HTTPS endpoints behind nginx, IIS or a cloud load balancer; wildcard certificates stored in a certificate manager.  
**Severity guidance:** P1 when a production certificate has expired (browsers block the site). P3 for a certificate expiring in less than 14 days with no alert.

## Detect
- Check the expiry date from outside the host:
  `echo | openssl s_client -servername <host> -connect <host>:443 2>/dev/null | openssl x509 -noout -dates`
- Expired certificates show `notAfter` in the past; browsers display `NET::ERR_CERT_DATE_INVALID`.
- If the site is behind Cloudflare in proxied (orange cloud) mode, the browser sees Cloudflare's edge certificate; the origin certificate is checked separately with `curl --resolve <host>:443:<origin-ip> https://<host>/ -vI`.

## Renew: Let's Encrypt with certbot (nginx hosts)
1. Dry run first: `sudo certbot renew --dry-run`.
2. Real renewal: `sudo certbot renew`. For a DNS-validated wildcard: `sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/cf.ini -d '*.<domain>' -d <domain>`.
3. Reload (not restart) nginx so existing connections are kept: `sudo nginx -t && sudo systemctl reload nginx`.
4. Verify with the openssl command from "Detect"; `notAfter` must be about 90 days ahead.

## Renew: wildcard certificate from a commercial CA (Windows / IIS / nginx on Windows)
1. Download the new certificate bundle from the CA portal as PFX (IIS) or PEM + key (nginx).
2. IIS: import the PFX into the Local Machine > Personal store, then update the HTTPS binding on the site to the new certificate, then `iisreset /noforce`.
3. nginx on Windows: replace the `ssl_certificate` and `ssl_certificate_key` files, run `nginx -t`, then `nginx -s reload`.
4. If the same wildcard is used on several hosts, renew all of them in the same change window and keep a list of hosts in the ticket.

## Prevent repeat incidents
- Add an uptime check with SSL expiry alerting (14 days and 7 days) for every public hostname.
- Keep the renewal credentials (DNS API token) in the secret store, never in the home directory of a shared account.
- Put the renewal procedure and the list of hosts for each wildcard in the certificate's ticket.
