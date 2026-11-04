// The pool is shared, so creating it per request leaks sockets.
var client = CreateClient();
