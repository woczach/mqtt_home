
  
local function encode(txn)
str = txn.get_var(txn,"txn.to_encode")  
core.Alert(string.format("clear  is %s", str))
Key53 = 8186484168865098  
Key14 = 4887
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
      core.Alert(string.format("encrypted  is %s", c))
      txn.set_var(txn,'txn.encoded',m)
      return ('%02x'):format(c)
    end
  ))
end
  
core.register_action("encode",{'http-req'}, encode, 0)
  
