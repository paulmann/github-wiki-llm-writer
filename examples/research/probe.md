# Probe report — php-mdviewer on /md.php

## modes

| request | status | bytes | ms | expected | ok |
|---|---|---|---|---|---|
| `GET /md.php` | **200** | 41808 | 11 | 200 | ✅ |
| `GET /md.php?file=docs/sub/deep.md` | **200** | 40582 | 1 | 200 | ✅ |
| `GET /md.php?file=md.md&download=1` | **200** | 53 | 1 | 200 | ✅ |
| `GET /md.php?file=../nope.md&download=1` | **404** | 15 | 1 | 404 | ✅ |
| `GET /md.php` | **200** | 41808 | 1 | 200 | ✅ |
| `GET /md.php` | **200** | 37301 | 1 | 200 | ✅ |
| `POST /md.php` | **200** | 36835 | 1 | 200 | ✅ |
| `POST /md.php` | **400** | 14 | 1 | 400 | ✅ |
| `GET //docs/x` | **404** | 540 | 1 | 301 | ❌ |
