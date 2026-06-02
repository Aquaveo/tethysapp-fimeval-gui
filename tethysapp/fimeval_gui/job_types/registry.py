class JobType:
    name: str

    def build_delayed(self, **params):
        raise NotImplementedError
