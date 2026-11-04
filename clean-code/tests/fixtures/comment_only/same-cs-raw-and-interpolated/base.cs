var raw = """
    keep // this text
    """; // remove this
var text = $"{items["key"]} // also text {{braces}}"; // remove
var nested = $@"{(flag ? "a" : "b")} C:\dir\"; // remove
