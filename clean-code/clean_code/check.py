from .context import CheckContext
from .findings import Finding
from .rules.comments import check_comments
from .rules.duplication import check_duplication
from .rules.external_tools import check_with_eslint, check_with_ruff
from .rules.functions import check_functions
from .rules.sizes import check_sizes

RULE_SETS = (check_comments, check_sizes, check_functions, check_duplication, check_with_ruff, check_with_eslint)


def run_checks(context: CheckContext) -> list[Finding]:
    findings = {finding for rule_set in RULE_SETS for finding in rule_set(context)}
    return sorted(findings, key=lambda finding: (not finding.blocking, finding.location.path, finding.location.line))
