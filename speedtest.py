#!/usr/bin/env python3
"""Measure HTTP download throughput with ten sequential requests."""

import argparse
import math
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class Measurement:
    seconds: float
    bytes_downloaded: int


@dataclass(frozen=True)
class Summary:
    count: int
    seconds: float
    bytes_downloaded: int

    @property
    def average_seconds(self):
        return self.seconds / self.count

    @property
    def megabytes_per_second(self):
        return self.bytes_downloaded / self.seconds / 1_000_000


def http_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        parsed.port  # Validate the port, if supplied.
    except ValueError:
        raise argparse.ArgumentTypeError(
            "provide an http:// or https:// URL without embedded credentials"
        ) from None
    return value


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError:
        timeout = 0
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def download(url, timeout):
    request = Request(url, headers={
        "User-Agent": "adrobot-speedtest/1.0",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
    })
    size = 0
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
    elapsed = time.perf_counter() - started
    if elapsed <= 0:
        raise RuntimeError("the measurement interval is too short")
    return Measurement(elapsed, size)


def summarize(measurements):
    if not measurements:
        raise ValueError("no successful measurements")
    seconds = sum(item.seconds for item in measurements)
    if seconds <= 0:
        raise ValueError("measurement time must be positive")
    return Summary(len(measurements), seconds,
                   sum(item.bytes_downloaded for item in measurements))


def run(url, timeout, output=sys.stdout, errors=sys.stderr):
    measurements = []
    for number in range(1, REQUEST_COUNT + 1):
        try:
            measurement = download(url, timeout)
        except (HTTPError, URLError, OSError, ValueError, RuntimeError) as error:
            print(f"Request {number}/{REQUEST_COUNT} failed: {error}", file=errors)
            print("Incomplete run; no final speed reported.", file=errors)
            return 1
        measurements.append(measurement)
        print(f"{number:2}/{REQUEST_COUNT}: {measurement.bytes_downloaded} bytes, "
              f"{measurement.seconds:.3f} s", file=output)

    result = summarize(measurements)
    print(f"\nSuccessful requests: {result.count}", file=output)
    print(f"Average request time: {result.average_seconds:.3f} s", file=output)
    print(f"Total request time: {result.seconds:.3f} s", file=output)
    print(f"Downloaded: {result.bytes_downloaded} bytes "
          f"({result.bytes_downloaded / 1_000_000:.3f} MB)", file=output)
    print(f"Speed: {result.megabytes_per_second:.3f} MB/s "
          f"({result.megabytes_per_second * 8:.3f} Mbit/s)", file=output)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=http_url, help="direct URL of a large file")
    parser.add_argument("--timeout", type=positive_timeout, default=30.0,
                        help="socket timeout in seconds (default: 30)")
    arguments = parser.parse_args()
    try:
        return run(arguments.url, arguments.timeout)
    except KeyboardInterrupt:
        print("\nMeasurement interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
