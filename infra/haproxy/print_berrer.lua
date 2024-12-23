local function print_berrer(txn)

    -------------------------------
    -- Get the auth code variable
    -------------------------------
    authcode = txn.get_var(txn,"txn.accesstoken")
    core.Alert(string.format("bereer is %s", authcode))
end

core.register_action("print_berrer",{'http-req'}, print_berrer, 0)
