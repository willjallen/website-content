#!/usr/bin/env python3
# minify-manim-svgs.py
#
# Off‑line optimiser for Manim‑generated JavaScript.
#  - Finds repeated token sequences *inside* setAttribute('d', …) calls
#  - Hoists them into constants D0, D1, … at the top of the file
#  - Rewrites every call site with string concatenation
#
# === tune me ================================================================
DEFAULT_MIN_NGRAM_LEN   = 7      # number of tokens in a candidate substring
DEFAULT_MIN_OCCURRENCES = 3      # keep only if it appears >= this many times
# ============================================================================

import re
import sys
import argparse
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Dict, Set

# Regex to find .setAttribute('d', ...) calls and extract the path string
D_CALL_RE = re.compile(
    r"\.setAttribute\(\s*['\"]d['\"]\s*,\s*(['\"])(.*?)\1\s*\)", re.S
)
# Regex to tokenize path strings into commands and numbers
TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?\d*\.\d+|[-+]?\d+")


def extract_d_path_strings(source_code: str) -> List[Tuple[str, str]]:
    """Extracts all ('full match text', path string) pairs from the source code."""
    return [(m.group(0), m.group(2)) for m in D_CALL_RE.finditer(source_code)]


def tokenize_paths(path_strings: List[str]) -> List[List[str]]:
    """Tokenizes each path string into commands and numbers."""
    return [TOKEN_RE.findall(path) for path in path_strings]


def get_ngrams(tokens: List[str], n: int) -> List[str]:
    """Generates n-grams from a list of tokens."""
    return [' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]


def find_candidate_ngrams(
    tokenized_paths: List[List[str]], min_ngram_len: int, min_occurrences: int
) -> Set[str]:
    """Counts n-gram occurrences and filters candidates."""
    counter = Counter()
    for tokens in tokenized_paths:
        counter.update(get_ngrams(tokens, min_ngram_len))
    return {s for s, c in counter.items() if c >= min_occurrences}


def build_dictionary_and_replace(
    source_code: str, candidates: Set[str], min_occurrences: int
) -> Tuple[str, Dict[str, str]]:
    """
    Greedily chooses non-overlapping substrings with the biggest savings
    and replaces them in the source code.
    Processes longer substrings first.
    """
    dictionary = {}
    # Ensure we have a mutable copy of source_code for replacements
    current_source_code = str(source_code)

    for cand_ngram in sorted(candidates, key=len, reverse=True):
        token_name = f"D{len(dictionary)}"
        # const Dx = '...';
        dict_entry_len = len(f"const {token_name} = '{cand_ngram}';")

        # Savings per occurrence: length of original - (length of token + quotes + two '+')
        # e.g., 'pathpart' -> '+' + Dx + '+'
        save_per_use = len(cand_ngram) - (len(token_name) + 3)
        if save_per_use <= 0:
            continue

        # Confirm the candidate still appears sufficiently often after previous replacements
        # Need to escape candidate string as it might contain regex special characters
        occurrences = list(re.finditer(re.escape(cand_ngram), current_source_code))
        if len(occurrences) < min_occurrences:
            continue

        dictionary[cand_ngram] = token_name
        # Replace occurrences in the current_source_code
        current_source_code = current_source_code.replace(cand_ngram, f"'+{token_name}+'")
    return current_source_code, dictionary


def cleanup_concatenation(source_code: str) -> str:
    """Cleans up spurious empty strings and extra pluses from concatenation."""
    # remove ''+ at the beginning of a concatenation
    cleaned_code = re.sub(r"''\+", '', source_code)
    # remove +'' at the end of a concatenation
    cleaned_code = cleaned_code.replace("+''", '')
    # remove +''+ in the middle of a concatenation (e.g. from "foo" + '' + "bar")
    cleaned_code = re.sub(r"\+''\+", '+', cleaned_code)
    return cleaned_code


def minify_svg_js(
    source_code: str, min_ngram_len: int, min_occurrences: int
) -> Tuple[str, Dict[str, str]]:
    """
    Minifies the SVG JS source code by deduplicating path strings.
    Returns the minified code and the dictionary of replacements.
    """
    original_path_calls = extract_d_path_strings(source_code)
    if not original_path_calls:
        print('No .setAttribute("d", ...) found in the input.', file=sys.stderr)
        return source_code, {}

    path_strings = [path for _, path in original_path_calls]
    tokenized_path_strings = tokenize_paths(path_strings)

    candidate_ngrams = find_candidate_ngrams(
        tokenized_path_strings, min_ngram_len, min_occurrences
    )

    if not candidate_ngrams:
        print(
            f"No candidate ngrams found with min_len={min_ngram_len} "
            f"and min_occurrences={min_occurrences}.",
            file=sys.stderr
        )
        return source_code, {}

    processed_source, replacement_dict = build_dictionary_and_replace(
        source_code, candidate_ngrams, min_occurrences
    )

    final_source = cleanup_concatenation(processed_source)
    return final_source, replacement_dict


def main():
    parser = argparse.ArgumentParser(
        description="Minify Manim-generated JavaScript by deduplicating SVG path data."
    )
    parser.add_argument(
        "input_js_path",
        type=Path,
        help="Path to the input JavaScript file."
    )
    parser.add_argument(
        "output_js_path",
        type=Path,
        nargs="?",
        help="Path to the output (deduplicated) JavaScript file. "
             "Defaults to input_js_path with '.dedup.js' suffix."
    )
    parser.add_argument(
        "--min-ngram-len",
        type=int,
        default=DEFAULT_MIN_NGRAM_LEN,
        help=f"Minimum number of tokens in a candidate substring (default: {DEFAULT_MIN_NGRAM_LEN})."
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=DEFAULT_MIN_OCCURRENCES,
        help=f"Minimum occurrences for an n-gram to be pooled (default: {DEFAULT_MIN_OCCURRENCES})."
    )
    parser.add_argument(
        "--search-ngram",
        action="store_true",
        help="Conduct a dynamic search for optimal MIN_NGRAM_LEN and MIN_OCCURRENCES "
             "to minimize file size. Overrides --min-ngram-len and --min-occurrences if set."
    )

    args = parser.parse_args()

    input_js_path: Path = args.input_js_path
    output_js_path: Path = (
        args.output_js_path
        if args.output_js_path
        else input_js_path.with_suffix(".dedup.js")
    )

    source_text = input_js_path.read_text()
    initial_size = len(source_text.encode('utf-8')) # More accurate than JS_PATH.stat().st_size

    if args.search_ngram:
        print("Searching for optimal n-gram parameters...")
        # Define search ranges (these can be tuned)
        ngram_len_range = range(3, 16)  # Example range for n-gram length
        occurrences_range = range(2, 8) # Example range for min occurrences

        best_params = (args.min_ngram_len, args.min_occurrences)
        smallest_size = float('inf')
        best_output_code = ""
        best_dictionary = {}

        for n_len in ngram_len_range:
            for n_occ in occurrences_range:
                print(f"  Trying MIN_NGRAM_LEN={n_len}, MIN_OCCURRENCES={n_occ}...")
                processed_source, current_dictionary = minify_svg_js(
                    source_text, n_len, n_occ
                )

                if not current_dictionary: # No savings if dictionary is empty
                    current_size = initial_size
                else:
                    header = '// === deduplicated path fragments ===\\n' + '\\n'.join(
                        f"const {t} = '{frag}';" for frag, t in current_dictionary.items()
                    ) + '\\n\\n'
                    full_output_code = header + processed_source
                    current_size = len(full_output_code.encode('utf-8'))

                if current_size < smallest_size:
                    smallest_size = current_size
                    best_params = (n_len, n_occ)
                    best_output_code = processed_source # Store source without header for now
                    best_dictionary = current_dictionary
                    print(
                        f"    New best: size {smallest_size/1e6:.3f} MB "
                        f"with N_LEN={n_len}, N_OCC={n_occ}, "
                        f"{len(best_dictionary)} fragments"
                    )
                elif current_size == smallest_size:
                     # Prefer more fragments if size is the same, as it implies more deduplication
                    if len(current_dictionary) > len(best_dictionary):
                        smallest_size = current_size
                        best_params = (n_len, n_occ)
                        best_output_code = processed_source
                        best_dictionary = current_dictionary
                        print(
                            f"    Found alternative best (more fragments): size {smallest_size/1e6:.3f} MB "
                            f"with N_LEN={n_len}, N_OCC={n_occ}, "
                            f"{len(best_dictionary)} fragments"
                        )


        final_min_ngram_len, final_min_occurrences = best_params
        final_processed_source = best_output_code
        final_dictionary = best_dictionary
        print(
            f"Search complete. Optimal parameters: "
            f"MIN_NGRAM_LEN={final_min_ngram_len}, MIN_OCCURRENCES={final_min_occurrences}"
        )

    else:
        final_min_ngram_len = args.min_ngram_len
        final_min_occurrences = args.min_occurrences
        final_processed_source, final_dictionary = minify_svg_js(
            source_text, final_min_ngram_len, final_min_occurrences
        )

    if not final_dictionary:
        print("No deduplication performed. Output file will be a copy of the input (or not written if different).")
        if output_js_path == input_js_path:
            print(f"Input and output paths are the same ({input_js_path}), no file written.")
            return
        # If we didn't make any changes and output is different, copy original
        # output_js_path.write_text(source_text)
        # print(f"Wrote copy to {output_js_path} - {initial_size/1e6:.1f} MB")
        # return

    # Stitch dictionary at the top
    header_lines = ['// === deduplicated path fragments ===']
    header_lines.extend(
        f"const {token} = '{fragment}';" for fragment, token in final_dictionary.items()
    )
    header = '\\n'.join(header_lines) + '\\n\\n'
    full_final_code = header + final_processed_source

    output_js_path.write_text(full_final_code)
    final_size = len(full_final_code.encode('utf-8'))

    print(
        f"Wrote {output_js_path} — {len(final_dictionary)} fragments pooled "
        f"(params: N_LEN={final_min_ngram_len}, N_OCC={final_min_occurrences}). "
        f"Size: {initial_size/1e6:.2f} MB → {final_size/1e6:.2f} MB. "
        f"Savings: {(initial_size - final_size)/1e6:.2f} MB ({(initial_size - final_size)/initial_size*100:.1f}%)"
    )

if __name__ == "__main__":
    main()
# --- extract every ('full match text', path string) pair -----------------
# --- tokenise each path string into commands + numbers -------------------
# --- count n‑gram occurrences -------------------------------------------
# --- greedily choose non‑overlapping substrings with biggest savings -----
# --- clean up the spurious ''+   '+ that appear at string ends ----------
# --- stitch dictionary at the top ---------------------------------------
