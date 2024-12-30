local function print_berrer(str)
    core.Alert(string.format("variable is %s", str))
end

core.register_converters("print_berrer", print_berrer)
