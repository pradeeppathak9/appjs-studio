import time, json, httpx
from app.database import SessionLocal
from app.models import PhonePeApp, PhonePeSubscription
from app.redis import redis_client
from app.api_handler.phonepe import PHONEPE_URLS, TOKEN_KEY_PREFIX

db = SessionLocal()
detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == '8efa16caabe540a0a1e3c8543daa0d2c').first()
subs = (db.query(PhonePeSubscription.id)
          .filter(PhonePeSubscription.app_id == detail.app_id,
                  PhonePeSubscription.state.in_(['INITIATED', 'ACTIVATION_IN_PROGRESS']))
          .limit(12).all())
ids = [s.id for s in subs]
db.close()

env = detail.phonepe_environment or 'UAT'
base = PHONEPE_URLS[env]['base'] if 'base' in PHONEPE_URLS[env] else PHONEPE_URLS[env].get('pg')
tok = json.loads(redis_client.get(f"{TOKEN_KEY_PREFIX}{detail.app_id}"))['access_token']
H = {'Authorization': f'O-Bearer {tok}', 'Content-Type': 'application/json'}
print('base url:', base, '| sample ids:', len(ids))

def url(i): return f"{base}/subscriptions/v2/{i}/status"

# A: current behaviour - new client (new TCP + TLS) per call
t0 = time.time()
for i in ids[:6]:
    with httpx.Client(timeout=30) as c:
        c.get(url(i), headers=H, params={'details': 'true'})
a = (time.time() - t0) / 6

# B: one client reused across calls (keep-alive)
t0 = time.time()
with httpx.Client(timeout=30) as c:
    for i in ids[6:12]:
        c.get(url(i), headers=H, params={'details': 'true'})
b = (time.time() - t0) / 6

print(f"  new client per call (current): {a*1000:7.1f} ms/req")
print(f"  reused client (keep-alive)   : {b*1000:7.1f} ms/req")
print(f"  handshake overhead per call  : {(a-b)*1000:7.1f} ms  ({(1-b/a)*100:.0f}% of each request)")
