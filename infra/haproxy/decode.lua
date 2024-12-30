do
  -- This is your secret 67-bit key (any random bits are OK)
  local Key53 = 8186484168865098
  local Key14 = 4887

  local inv256
  local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/' -- You will need this for encoding/decoding

  function b64enc(data)
    return ((data:gsub('.', function(x) 
        local r,b='',x:byte()
        for i=8,1,-1 do r=r..(b%2^i-b%2^(i-1)>0 and '1' or '0') end
        return r;
    end)..'0000'):gsub('%d%d%d?%d?%d?%d?', function(x)
        if (#x < 6) then return '' end
        local c=0
        for i=1,6 do c=c+(x:sub(i,i)=='1' and 2^(6-i) or 0) end
        return b:sub(c+1,c+1)
    end)..({ '', '==', '=' })[#data%3+1])
end

-- decoding
function b64dec(data)
    data = string.gsub(data, '[^'..b..'=]', '')
    return (data:gsub('.', function(x)
        if (x == '=') then return '' end
        local r,f='',(b:find(x)-1)
        for i=6,1,-1 do r=r..(f%2^i-f%2^(i-1)>0 and '1' or '0') end
        return r;
    end):gsub('%d%d%d?%d?%d?%d?%d?%d?', function(x)
        if (#x ~= 8) then return '' end
        local c=0
        for i=1,8 do c=c+(x:sub(i,i)=='1' and 2^(8-i) or 0) end
            return string.char(c)
    end))
end

  function encrypt(str)
    if not inv256 then
      inv256 = {}
      for M = 0, 127 do
        local inv = -1
        repeat inv = inv + 2
        until inv * (2*M + 1) % 256 == 1
        inv256[M] = inv
      end
    end
    local K, F = Key53, 16384 + Key14
    return (str:gsub('.',
      function(m)
        local L = K % 274877906944  -- 2^38
        local H = (K - L) / 274877906944
        local M = H % 128
        m = m:byte()
        local c = (m * inv256[M] - (H - M) / 128) % 256
        K = L * F + H + c + m
        return ('%02x'):format(c)
      end
    ))
  end




  function decode(str)
    local K, F = Key53, 16384 + Key14
    return (str:gsub('%x%x',
      function(c)
        local L = K % 274877906944  -- 2^38
        local H = (K - L) / 274877906944
        local M = H % 128
        c = tonumber(c, 16)
        local m = (c + (H - M) / 128) * (2*M + 1) % 256
        K = L * F + H + c + m
        return string.char(m)
      end
    ))
  end
end

function split_string(input_str, delimiter)
  if delimiter == '' then return {input_str} end
  local result = {}
  local pattern = string.format("([^%s]+)", delimiter)
  for match in (input_str):gmatch(pattern) do
      table.insert(result, match)
  end
  return result
end

function return_permissions(str)
  return split_string(b64dec(decode(str)),'-')[2]
end

function return_timestamp(str)
  return split_string(b64dec(decode(str)),'-')[1]
end

function encode(str)
  return encrypt(b64enc(str))
end


-- local s = 'Hello world'
-- print(       encode(s) ) --> 80897dfa1dd85ec196bc84
-- print(decode(encode(s))) --> Hello world
core.register_converters("return_permissions", return_permissions)
core.register_converters("return_timestamp", return_timestamp)
core.register_converters("encode", encode)
core.register_converters("decode", decode)