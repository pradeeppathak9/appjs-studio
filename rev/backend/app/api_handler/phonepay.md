curl --location 'https://api.phonepe.com/apis/identity-manager/v1/oauth/token' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode 'client_id=YOUR_CLIENT_ID' \
--data-urlencode 'client_version=1' \
--data-urlencode 'client_secret=YOUR_CLIENT_SECRET' \
--data-urlencode 'grant_type=client_credentials'



{"access_token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJpZGVudGl0eU1hbmFnZXIiLCJ2ZXJzaW9uIjoiNC4wIiwidGlkIjoiZDEwNWNkN2UtZjVlMS00NmU1LWFkNmMtNjIzZGYzMjg0OTQ0Iiwic2lkIjoiNWUzNzdjMTktZjY1Zi00NGNjLTg5Y2EtMmViMGZjODkxYjEyIiwiaWF0IjoxNzg2NDY5MzE1LCJleHAiOjE3ODY0NzI5MTV9.uywg0pwcJ1mWLGEayr40SRctAxXwlMcOMSJKK9Hhpinlu9UNdKYNkLH8lefGPsaooCVO0WfupJ5UEFiLhh5AIQ","encrypted_access_token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJpZGVudGl0eU1hbmFnZXIiLCJ2ZXJzaW9uIjoiNC4wIiwidGlkIjoiZDEwNWNkN2UtZjVlMS00NmU1LWFkNmMtNjIzZGYzMjg0OTQ0Iiwic2lkIjoiNWUzNzdjMTktZjY1Zi00NGNjLTg5Y2EtMmViMGZjODkxYjEyIiwiaWF0IjoxNzg2NDY5MzE1LCJleHAiOjE3ODY0NzI5MTV9.uywg0pwcJ1mWLGEayr40SRctAxXwlMcOMSJKK9Hhpinlu9UNdKYNkLH8lefGPsaooCVO0WfupJ5UEFiLhh5AIQ","refresh_token":"30bc6221-53dc-495e-a6e4-77969e14ce44","expires_in":3600,"issued_at":1786469315,"expires_at":1786472915,"session_expires_at":1786472915,"token_type":"O-Bearer"}p


curl --location 'https://api.phonepe.com/apis/pg/subscriptions/v2/setup' \
--header 'Accept: application/json' \
--header 'Authorization: O-Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJpZGVudGl0eU1hbmFnZXIiLCJ2ZXJzaW9uIjoiNC4wIiwidGlkIjoiZDEwNWNkN2UtZjVlMS00NmU1LWFkNmMtNjIzZGYzMjg0OTQ0Iiwic2lkIjoiNWUzNzdjMTktZjY1Zi00NGNjLTg5Y2EtMmViMGZjODkxYjEyIiwiaWF0IjoxNzg2NDY5MzE1LCJleHAiOjE3ODY0NzI5MTV9.uywg0pwcJ1mWLGEayr40SRctAxXwlMcOMSJKK9Hhpinlu9UNdKYNkLH8lefGPsaooCVO0WfupJ5UEFiLhh5AIQ' \
--header 'Content-Type: application/json' \
--data '{
   "merchantOrderId": "MO1443709025658932",
   "amount": 200,
   "expireAt": 170905854,
   "paymentFlow": {
       "type": "SUBSCRIPTION_SETUP",
       "merchantSubscriptionId": "MS1709025658932",
       "authWorkflowType": "TRANSACTION",
       "amountType": "FIXED",
       "maxAmount": 200,
       "frequency": "ON_DEMAND",
       "expireAt": 1737278524000,
       "paymentMode": {
           "type": "UPI_INTENT",
           "targetApp": "com.phonepe.app"
       }
   },
    "deviceContext" : {
        "deviceOS" : "ANDROID"
    }
}'