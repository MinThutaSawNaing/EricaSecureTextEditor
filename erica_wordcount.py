"""Incremental per-block word totals; cursor movement never scans document text."""
from erica_storage import count_words


class DocumentWordCounter:
    def __init__(self, document):
        self.document = document
        self.counts = []
        block = document.begin()
        while block.isValid():
            self.counts.append(count_words(block.text()))
            block = block.next()
        self.total = sum(self.counts)
        document.contentsChange.connect(self._changed)

    def _changed(self, position, removed, added):
        document = self.document
        start = document.findBlock(min(position, document.characterCount() - 1))
        end = document.findBlock(min(position + added, document.characterCount() - 1))
        first = start.blockNumber()
        new_counts = []
        block = start
        while block.isValid() and block.blockNumber() <= end.blockNumber():
            new_counts.append(count_words(block.text()))
            block = block.next()
        old_length = len(self.counts) - document.blockCount() + len(new_counts)
        previous = self.counts[first:first + old_length]
        self.counts[first:first + old_length] = new_counts
        self.total += sum(new_counts) - sum(previous)