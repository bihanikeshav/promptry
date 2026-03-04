from promptry.writer import AsyncWriter


class TestAsyncWriter:

    def test_write_and_flush(self, storage):
        writer = AsyncWriter(storage)
        writer.save_prompt("test", "hello", "abc123")
        writer.flush()

        record = storage.get_prompt("test")
        assert record is not None
        assert record.content == "hello"

    def test_reads_go_through(self, storage):
        storage.save_prompt("direct", "content", "hash123")
        writer = AsyncWriter(storage)

        record = writer.get_prompt("direct")
        assert record.content == "content"
