"""Import the authorized source without printing paths, secrets, PDI, or raw rows."""
import argparse
import json
import os

from twinops.demo.importer import import_history
from twinops.demo.repository import DemoRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--expected-hash', required=True)
    parser.add_argument('--timezone', default='America/Sao_Paulo')
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    url = os.environ.get('DEMO_DATABASE_URL') or os.environ.get('TWINOPS_DATABASE_URL')
    if not url:
        parser.error('set DEMO_DATABASE_URL or TWINOPS_DATABASE_URL')
    repository = DemoRepository(url, initialize=False)
    if args.initialize:
        repository.initialize()
    metadata = import_history(args.source, repository, timezone_name=args.timezone, expected_hash=args.expected_hash)
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == '__main__':
    main()
