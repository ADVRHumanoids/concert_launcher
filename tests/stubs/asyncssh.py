"""Small AsyncSSH test double used in the offline test environment."""


class Error(Exception):
    pass


class ChannelOpenError(Error):
    def __init__(self, reason="channel error"):
        self.reason = reason
        super().__init__(reason)


class SSHClientConnection:
    pass


async def connect(**kwargs):
    raise NotImplementedError(kwargs)


async def scp(*args, **kwargs):
    return None
