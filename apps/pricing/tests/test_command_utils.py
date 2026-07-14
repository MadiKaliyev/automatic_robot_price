from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.pricing.management.command_utils import (
    parse_children_ages,
)


class ParseChildrenAgesTests(SimpleTestCase):
    def test_parses_comma_separated_ages(self):
        self.assertEqual(
            parse_children_ages("4, 9"),
            (4, 9),
        )

    def test_rejects_invalid_age(self):
        with self.assertRaises(CommandError):
            parse_children_ages("18")
