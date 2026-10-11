"""Explicit local/admin commands; never import an arbitrary browser-supplied path."""
import argparse
import json

from .templates import import_reviewed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-reviewed', required=True, help='Accepted map package directory')
    parser.add_argument('--data-root', required=True, help='New runtime persistent volume directory')
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--grant-town-id', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    revision = import_reviewed(args.import_reviewed, args.data_root, args.source_id, args.name, args.grant_town_id)
    print(json.dumps({'sourceId': args.source_id, 'sourceRevision': revision}))


if __name__ == '__main__':
    main()
