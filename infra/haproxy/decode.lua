
  
local  function decode(txn)
    str = txn.get_var(txn,"txn.to_decode")  
    core.Alert(string.format("to be decoded  is %s", str))
    Key53 = 8186484168865098
    Key14 = 4887      
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

core.Alert(string.format("decoded is %s", string.char(m)))
txn.set_var(txn,'txn.decoded',string.char(m))  
core.register_action("decode",{'http-req'}, decode, 0)