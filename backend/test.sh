curl -X 'GET' \
  "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials" \
  -H "accept: application/json" \
  -H "Authorization: ${AUTHORIZATION_HEADER}"