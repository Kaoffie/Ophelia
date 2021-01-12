"""
Substring spam utilities module.

This module implements the Ukkonen's algorithm for building suffix trees
and traverses suffix trees to find repeated substrings. The way this
method finds substrings is not perfect, but it's certainly serviceable.
I couldn't think of a solution that could generate the exact numbers
without having it go to O(n^2), which would have been horrible for any
spammers who could easily just slow the whole system down.

The suffix tree implementation is based on the implementation found
here: https://github.com/kvh/Python-Suffix-Tree; below is the license
for the code used and applies to the implementation in lines 46 to 258
(Pylink's too few public methods refactor is intentionally ignored here
since we're following original implementation):


Copyright (c) 2012 Ken Van Haren

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from typing import List, Tuple, Dict, Set

from ophelia import settings


# pylint: disable=too-few-public-methods
class SuffixNode:
    """Suffix tree node."""

    __slots__ = ["index"]

    def __init__(self) -> None:
        """Initializer for the SuffixNode class."""
        self.index = -1


class SuffixEdge:
    """Suffix tree edge."""

    __slots__ = ["start_index", "end_index", "source_index", "dest_index"]

    def __init__(
            self,
            start_index: int,
            end_index: int,
            source_index: int,
            dest_index: int
    ) -> None:
        """
        Initializer for the SuffixEdge class.

        :param start_index: Starting index in source string
        :param end_index: End index in source string
        :param source_index: Edge source node
        :param dest_index: Edge destination node
        """
        self.start_index = start_index
        self.end_index = end_index
        self.source_index = source_index
        self.dest_index = dest_index

    def __len__(self) -> int:
        """Get length of substring represented by edge."""
        return self.end_index - self.start_index


class Suffix:
    """Suffix from a given pair of indices."""

    __slots__ = ["start_index", "end_index", "source_index"]

    def __init__(
            self,
            start_index: int,
            end_index: int,
            source_index: int
    ) -> None:
        """
        Initializer for the Suffix class.

        :param start_index: Start index of substring
        :param end_index: End index of substring
        :param source_index: Substring source node index
        """
        self.start_index = start_index
        self.end_index = end_index
        self.source_index = source_index

    def __len__(self) -> int:
        """Get length of substring."""
        return self.end_index - self.start_index

    def is_explicit(self) -> bool:
        """Check if suffix is explicit."""
        return self.start_index > self.end_index

    def is_implicit(self) -> bool:
        """Check if suffix is implicit."""
        return self.start_index <= self.end_index


class SuffixTree:
    """Suffix tree for counting substrings."""

    __slots__ = [
        "text",
        "tail_index",
        "nodes",
        "edges",
        "active",
        "index"
    ]

    def __init__(self, text: str) -> None:
        """
        Initializer for the SuffixTree class.

        :param text: Suffix tree source text
        """
        self.text = text
        self.tail_index = len(text) - 1
        self.nodes: List[SuffixNode] = [SuffixNode()]
        self.edges: Dict[Tuple[int, str], SuffixEdge] = {}
        self.active = Suffix(0, -1, 0)

        for i in range(len(text)):
            self.consume_char(i)

    def consume_char(self, last_index: int) -> None:
        """
        Add character to suffix tree.

        :param last_index: Last character index
        """
        last_parent_node = -1
        while True:
            parent_node = self.active.source_index
            if self.active.is_explicit():
                if (
                        (self.active.source_index, self.text[last_index])
                        in self.edges
                ):
                    break

            else:
                edge = self.edges[
                    self.active.source_index,
                    self.text[self.active.start_index]
                ]

                if (
                        self.text[edge.start_index + len(self.active) + 1]
                        == self.text[last_index]
                ):
                    break

                parent_node = self.split_edge(edge, self.active)

            self.nodes.append(SuffixNode())
            edge = SuffixEdge(
                start_index=last_index,
                end_index=self.tail_index,
                source_index=parent_node,
                dest_index=len(self.nodes) - 1
            )
            self.insert_edge(edge)

            if last_parent_node > 0:
                self.nodes[last_parent_node].index = parent_node
            last_parent_node = parent_node

            if self.active.source_index == 0:
                self.active.start_index += 1
            else:
                self.active.source_index = (
                    self.nodes[self.active.source_index].index
                )
            self.canonize_suffix(self.active)

        if last_parent_node > 0:
            self.nodes[last_parent_node].index = parent_node

        self.active.end_index += 1
        self.canonize_suffix(self.active)

    def insert_edge(self, edge: SuffixEdge) -> None:
        """
        Insert edge into tree.

        :param edge: Edge to insert
        """
        self.edges[(edge.source_index, self.text[edge.start_index])] = edge

    def remove_edge(self, edge: SuffixEdge) -> None:
        """
        Remove edge from tree.

        :param edge: Edge to remove
        """
        self.edges.pop((edge.source_index, self.text[edge.start_index]), None)

    def split_edge(self, edge: SuffixEdge, suffix: Suffix) -> int:
        """
        Split an edge to insert a new edge.

        :param edge: Edge to split
        :param suffix: Suffix reference
        :return Destination index of newly inserted edge
        """
        self.nodes.append(SuffixNode())
        new_edge = SuffixEdge(
            start_index=edge.start_index,
            end_index=edge.start_index + len(suffix),
            source_index=suffix.source_index,
            dest_index=len(self.nodes) - 1
        )

        self.remove_edge(edge)
        self.insert_edge(new_edge)
        self.nodes[new_edge.dest_index].index = suffix.source_index
        edge.start_index += len(suffix) + 1
        edge.source_index = new_edge.dest_index
        self.insert_edge(edge)

        return new_edge.dest_index

    def canonize_suffix(self, suffix: Suffix) -> None:
        """
        Canonize suffix.

        :param suffix: Suffix to canonize
        """
        if not suffix.is_explicit():
            edge = self.edges[
                suffix.source_index, self.text[suffix.start_index]]
            if len(edge) <= len(suffix):
                suffix.start_index += len(edge) + 1
                suffix.source_index = edge.dest_index
                self.canonize_suffix(suffix)

    def max_rep_substrings(
            self,
            stop_limit: int,
            min_len: int,
            max_len: int
    ) -> Tuple[str, int, int]:
        """
        Find the most repeated substring.

        :param stop_limit: Repeated length limit to stop at even if
            there are other substrings that have been repeated more
            times than this; typically set at the severe flag level
        :param min_len: Minimum substring length
        :param max_len: Maximum substring length
        :return: Tuple of repeated substring, the number of repetitions,
            and the total number of repeated characters
        """
        parental_map: Dict[int, int] = {}
        child_map: Dict[int, List[int]] = {}
        rep_set: Set[int] = set()
        local_suffix: Dict[int, str] = {0: ""}

        edge_counter = 0
        for (e_node, _), c_edge in self.edges.items():
            edge_counter += 1
            dest = c_edge.dest_index
            parental_map[dest] = e_node
            child_map.setdefault(e_node, []).append(dest)

            local_suffix[dest] = (
                self.text[c_edge.start_index:c_edge.end_index + 1]
            )

            if c_edge.end_index == self.tail_index:
                rep_set.add(e_node)

        substring_log: Dict[int, str] = {0: ""}
        max_substring = ""
        max_rep_count = 0
        max_rep_chars = 0
        next_layer = [0]
        while child_map:
            next_next_layer = []

            # Parent loop
            for parent in next_layer:
                if parent not in child_map:
                    # Continue parent loop
                    continue

                children = child_map.pop(parent)
                next_next_layer += children

                # Child loop
                for child in children:
                    substring = (
                            substring_log[parent] + local_suffix[child]
                    )

                    substring_log[child] = substring
                    substring_len = len(substring)
                    if not min_len <= substring_len <= max_len:
                        # Continue child loop
                        continue

                    rep_count = self.text.count(substring)
                    if rep_count <= 1:
                        # Continue child loop
                        continue

                    rep_chars = rep_count * substring_len

                    if rep_chars >= stop_limit:
                        return substring, rep_count, rep_chars

                    if rep_chars > max_rep_chars:
                        max_substring = substring
                        max_rep_count = rep_count
                        max_rep_chars = rep_chars

            next_layer = next_next_layer

        return max_substring, max_rep_count, max_rep_chars

    @classmethod
    async def find_substring_spam(
            cls,
            text: str,
            hard_limit: int = settings.substring_hard_limit,
            stop_limit: int = settings.substring_stop_limit,
            min_len: int = settings.substring_min_len,
            max_len: int = settings.substring_max_len
    ) -> Tuple[str, int, int, float]:
        """
        Find the most spammed substring within a longer string.

        :param text: String to search for substrings in
        :param hard_limit: Maximum string length to analyze. Strings
            longer than this limit will be spliced from the end; this
            is set so that messages won't take too long to analyze
            (theoretical maximum is the max cache size times 2000 but
            that will not work
        :param stop_limit: Repeated length limit to stop at even if
            there are other substrings that have been repeated more
            times than this; typically set at the severe flag level
        :param min_len: Minimum substring length
        :param max_len: Maximum substring length
        :return: A tuple of the most spammed string, the number of times
            it has been repeated in the string, the total number of
            characters taken by that substring, and the proportion of
            the analyzed text taken up by that substring
        """
        text_len = len(text)
        if text_len > hard_limit:
            text = text[-hard_limit:]

        # Find first private use area character that's not in string
        for priv_ord in range(0xE000, 0xF8FF):
            priv_chr = chr(priv_ord)
            if priv_chr not in text:
                text += priv_chr
                break

        suffix_tree = cls(text)
        substr, rep_count, rep_chars = suffix_tree.max_rep_substrings(
            stop_limit,
            min_len,
            max_len
        )

        rep_prop = rep_chars / text_len
        return substr, rep_count, rep_chars, rep_prop

# Further optimizations - find the substrings while building tree
