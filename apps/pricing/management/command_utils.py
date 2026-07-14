from django.core.management.base import CommandError


def parse_children_ages(value: str | None) -> tuple[int, ...]:
    if not value or not value.strip():
        return ()

    try:
        ages = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as error:
        raise CommandError(
            "Возраст детей нужно указать числами через запятую, например: 4,9."
        ) from error

    if len(ages) > 3:
        raise CommandError("Поддерживается не более трёх детей.")

    if any(age < 0 or age > 17 for age in ages):
        raise CommandError("Возраст каждого ребёнка должен быть от 0 до 17 лет.")

    return ages
