// A cancelled execution may have no final receipt. Preserve that fact;
// the fresh remote plan will reconcile state without fabricating one.
int retries = 3;
