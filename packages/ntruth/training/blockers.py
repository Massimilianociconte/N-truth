"""Canonical operational blocker identifiers shared by training components."""

FD_ISOLATION_BLOCKER_CODE = "anonymous_unlinked_inherited_fd_runner"
FD_ISOLATION_BLOCKER_DETAIL = (
    "operazione MLX bloccata: isolamento post-validazione non FD-safe; "
    "serve un runner privato che consumi esclusivamente file descriptor read-only "
    "anonimi/unlinked ereditati"
)
