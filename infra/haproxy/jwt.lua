local jwt = require("jwt")

function parse_jwt(txn)
    local auth_header = txn.sf:req_hdr("Authorization")
    if not auth_header then
        txn:set_var("txn.auth_status", "unauthenticated")
        return
    end

    local token = string.match(auth_header, "Bearer%s+(.+)")
    if not token then
        txn:set_var("txn.auth_status", "unauthenticated")
        return
    end

    -- Decode and validate the token
    local decoded, err = jwt.decode(token, { keys = nil, allowed_alg = "RS256" })
    if not decoded then
        txn:set_var("txn.auth_status", "invalid")
        return
    end

    -- Extract claims
    local username = decoded.payload["preferred_username"] or "unknown"
    local roles = decoded.payload["roles"] or {}

    -- Set variables for routing
    txn:set_var("txn.auth_status", "authenticated")
    txn:set_var("txn.username", username)
    txn:set_var("txn.role", table.concat(roles, ","))
end
