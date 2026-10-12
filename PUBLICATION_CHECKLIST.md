# Owner-gated publication checklist

Nothing in this checklist has been executed.

## A. Create public GitHub repository

- Repository name: `miden-preflight`
- Suggested description: Compatibility and migration preflight for Miden builders.
- Suggested visibility: public
- Owner approval required: yes

## B. Push sanitized source

- Source: this package directory only
- Required pre-push gates: tests pass, demos pass, secret scan passes, owner reviews public transaction evidence
- Owner approval required: yes, separately from repository creation

## C. Deploy landing page

- Recommendation: **GitHub Pages** from `website/`
- Reason: the site is static, buildless, and belongs beside the source; Pages adds no runtime, secret, or external deployment dependency.
- Owner approval required: yes, separately from source push

## D. Optional upstream contribution

- Best first candidate: Web SDK wallet lockfile alignment, subject to maintainer-intent confirmation
- Alternative: midenup Windows PATH patch after Windows MSVC CI validation
- Owner approval required: yes for each issue, pull request, or maintainer contact
