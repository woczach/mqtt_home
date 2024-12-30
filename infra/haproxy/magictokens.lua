local function magictokens(txn)

    -------------------------------
    -- Get the auth code variable
    -------------------------------
    authcode = txn.get_var(txn,"req.authcode")
    redirect_uri = txn.get_var(txn,"req.redirect_addr")
    -- core.Debug(string."auth code is authcode")

    -------------------------------
    -- Prepare token request
    -------------------------------
    -- http://localhost:8080/realms/myrealm/protocol/openid-connect/token

    client_id_and_secret = "Z3JhZmFuYTpoTnlvbFVEYTJBZ1pGQ0RJTXkyZ09rSGJNeFFRZGY2Mw=="
    realm = "master"
    token_endpoint = string.format("/realms/%s/protocol/openid-connect/token",realm)
    client_id="grafana"
    grant_type="authorization_code"
    -- redirect_uri="http://grafana.purpucle.pl:8085/"
    data=string.format("grant_type=%s&client_id=%s&redirect_uri=%s&code=%s",grant_type,client_id,redirect_uri,authcode)
    accepting = "Host: 192.168.0.230:7080"
    auth_header = string.format("Authorization: Basic %s",client_id_and_secret)
    content_length_header = string.format("Content-Length: %d", string.len(data))
    content_type_header = "Content-Type: application/x-www-form-urlencoded"

    token_request = string.format("POST %s HTTP/1.1\r\n%s\r\n%s\r\n%s\r\n%s\r\n\r\n%s",token_endpoint,accepting,auth_header,content_type_header,content_length_header,data)

    core.Alert(string.format("request is %s", token_request))
    
    -------------------------------
    -- Make request over TCP
    -------------------------------
    contentlen = 0

    idp = core.tcp()
    idp:settimeout(5)
    -- connect to issuer
    if idp:connect('192.168.0.230','7080') then
      if idp:send(token_request) then
      
        -- Skip response headers
        while true do
          local line, err = idp:receive('*l')

          if err then
            core.Alert(string.format("error reading header: %s",err))
            break
          else
            if line then
              --core.Debug(string."data: line")
              if line == '' then break end
              -- core.Debug(string."substr: string.sub(line,1,3)")
              if string.sub(string.lower(line),1,15) == 'content-length:' then
                --core.Debug(string."found content-length: string.sub(line,16)")
                contentlen = tonumber(string.sub(line,16))
              end
            else
              --core.Debug("no more data")
              break
            end
          end
        end

        -- Get response body, if any
        --core.Debug("read body")
        local content, err = idp:receive(contentlen)

        if content then
          -- save the entire token response out to a variable for
          -- further processing in haproxy.cfg
          --core.Debug(string."tokens are content")
          txn.set_var(txn,'req.tokenresponse',content)
          core.Alert(string.format("content is : %s",content))
        else
          core.Alert(string.format("error receiving tokens: %s",err))
        end
      else
          core.Alert('Could not send to IdP (send)')
      end
      idp:close()
    else
        core.Alert('Could not connect to IdP (connect)')
    end

end

core.register_action("magictokens",{'http-req'}, magictokens, 0)
