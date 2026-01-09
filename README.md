
# DoD Prohibited Dietary Supplement Ingredients Project

This project provides an easy-to-browse, searchable, and regularly updated list of substances prohibited by the Department of Defense (DoD) for use in dietary supplements. **This tool exists because the DoD's own Operation Supplement Safety (OPSS) system has failed service members** by directing people to a poorly designed webpage/database as its source of truth.

As detailed in [Task & Purpose's investigation](https://taskandpurpose.com/opinion/secret-list-ending-military-careers/) and discussed on Reddit (see posts on [r/USMC](https://www.reddit.com/r/USMC/comments/1p28zlq/the_secret_list_thats_ending_military_careers/) and [r/navy](https://www.reddit.com/r/navy/comments/1pza544/the_secret_list_thats_ending_military_careers/)), the DoD's prohibited ingredients system has a few critical flaws:

- **No product search capability** - You can't search by supplement brand name, only by obscure chemical ingredients
- **Unforgiving search system** - A single typo means a banned substance won't be flagged (e.g., "enlcomiphene" vs "enclomiphene")
- **No autocorrect or user guidance** - The system provides no help for complex chemical names
- **Automatic career termination** - Once caught with a prohibited substance, separation is often mandatory regardless of circumstances
- **No real due process** - Many service members don't even get a hearing


## What does this project do?

- **Retrieves** the official DoD prohibited ingredients list from the [OPSS website](https://www.opss.org/dod-prohibited-dietary-supplement-ingredients)
- **Makes it actually searchable** - Unlike OPSS, you can search by substance names, not just chemical formulas
- **Provides clear substance pages** with comprehensive information including UNII database links when available
- **Generates** a user-friendly website with proper navigation and search functionality
- **Updates** automatically every day to catch new additions to the prohibited list
- **Offers the transparency and usability** that service members deserve but aren't getting from the official system

## The Bigger Picture

While this tool helps individual service members navigate the prohibited substances list, the real solution requires systemic change:

- **Education over punishment** - First-time violations should be treated as health and welfare issues, not misconduct
- **Fix the official OPSS system** - Add product search, autocorrect, and clear guidance  
- **End automatic separation** - Commands should have discretion based on circumstances
- **Provide real due process** - Service members deserve actual hearings, not just written statements
- **Focus on the mission** - Stop driving out dedicated troops over administrative failures

As military defense counsel Captain Max Jesse Goldberg wrote: *"The Defense Department says it wants fit, resilient service members. Yet we ruin careers for doing exactly what we demand: getting ready for the next fight."*

## How does it work?

1. **Retrieval**: Every day, at least once, it downloads the latest data from the official DoD OPSS page
2. **Parsing**: Extracts and cleans up the data into a usable format
3. **Enhancement**: Adds additional information like UNII database links for better substance identification
4. **Generation**: Creates an actually navigable website that service members can use

## For Service Members

**⚠️ IMPORTANT DISCLAIMER**: While this tool makes the prohibited list more accessible, **always verify any supplement with your command before use**. The official OPSS system, despite its flaws, remains the authoritative source. When in doubt, don't risk your career - ask your SACO (Substance Abuse Control Officer) or medical personnel.

**This project cannot prevent all supplement-related incidents**, but it can help you:

- Quickly search for substances by name (not just chemical formulas)
- Understand what substances are prohibited and why
- Access additional scientific information through UNII database links
- Stay updated on new additions to the prohibited list

## For Advocates and Policymakers

If you're working to fix this systemic problem:

- **Share stories** - Document cases of good service members being hurt by this broken system
- **Support reform** - Push for education-first policies and discretion in enforcement
- **Demand accountability** - The current system is failing the very people it was meant to protect
- **Use this data** - Our structured data can support research and policy arguments

## For contributors and technical users

- The code is split into three main modules:
  - `retrieval.py`: Handles downloading the data from the source.
  - `parsing.py`: Extracts and cleans the data.
  - `generation.py`: Generates the website content and changelog.
- The main script (`generate_docs.py`) ties these together.
- To run locally:
  1. Install dependencies with `uv pip install -r requirements.txt --system && uv pip install -r requirements-docs.txt --system`
  2. Run `python generate_docs.py`
  3. Serve the site with `mkdocs serve`

## License

This project is open source and available under the MIT License. See [LICENSE](LICENSE.md).

## Sources and Further Reading

- [Task & Purpose: "The secret list that's ending military careers"](https://taskandpurpose.com/opinion/secret-list-ending-military-careers/)
- [r/USMC Discussion Thread](https://www.reddit.com/r/USMC/comments/1p28zlq/the_secret_list_thats_ending_military_careers/)
- [Official OPSS Website](https://www.opss.org/dod-prohibited-dietary-supplement-ingredients) (the flawed system we're trying to fix)
- [DoD Instruction 6130.06](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/613006p.PDF) (the policy behind the enforcement)

## Contact

For questions, suggestions, or to report supplement-related incidents, open an issue or pull request on [GitHub](https://github.com/gooosetavo/dod-prohibited).

**If you're a service member facing separation over supplement use**, contact base legal services or a military defense counsel immediately. You have rights, even if the system doesn't make that clear.
