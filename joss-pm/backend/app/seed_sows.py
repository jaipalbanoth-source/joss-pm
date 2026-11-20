"""Fictional sample SOWs (used for demo + automated tests). Names, amounts and dates are illustrative."""

ACME = """STATEMENT OF WORK
Oracle Fusion Financials Implementation
SOW-2026-0457 | Acme Corp Ltd / Jade Global

1. Parties and Effective Date
This Statement of Work is made between Acme Corp Ltd ("Client") and Jade Global ("Jade Global") under the Master Services Agreement.
The project will commence on November 1, 2026.

2. Scope of Work
Jade Global will implement Oracle Fusion Cloud Financials for Acme Corp Ltd, covering General Ledger, Accounts Payable, Accounts Receivable and Fixed Assets. The scope includes requirements workshops, solution design, configuration, up to 5 reports and 3 integrations, data migration, three test cycles (SIT, UAT, regression) and go-live support. Procurement, Projects and Supply Chain modules are out of scope.

3. Approach and Phases
Jade Global will follow a hybrid Agile methodology with a fixed milestone plan.
Work is organised in five phases:
1. Discovery and Design - Nov 2026 - Dec 2026
2. Build and Configure - Dec 2026 - Jan 2027
3. Test (SIT, UAT, regression, 3 test cycles) - Jan 2027 - Mar 2027
4. Cutover and Go-Live - Mar 2027
5. Hypercare - 4 weeks, ending March 31, 2027

4. Deliverables and Milestones
M1 Signed-off solution design document - December 15, 2026 - 20%
M2 Configured system and integrations ready for SIT - January 29, 2027 - 25%
M3 UAT completed and signed off - March 5, 2027 - 25%
M4 Production go-live - March 15, 2027 - 20%
M5 Hypercare completed and project closure - March 31, 2027 - 10%

5. Commercial Terms
This engagement is on a Fixed Price basis. The total fixed fee is USD 480,000, exclusive of applicable taxes.
The fee is payable by milestone as set out in Section 4. Invoices must quote the Client's Purchase Order No. PO-88231.

6. Change Control and Tolerance
Any change to scope, schedule or fees must be recorded in a written change request approved by both Parties.
Jade Global may absorb effort variance within a tolerance of 5% of planned effort per phase without a change request.

7. Team and Governance
A weekly status meeting and a monthly steering committee review will be held throughout the term.
"""

GLOBEX = """STATEMENT OF WORK
Globex Salesforce Sales Cloud Optimisation
SOW-2026-0462 | Globex Corporation / Jade Global

1. Parties
This Statement of Work is entered into between Globex Corporation ("Client") and Jade Global.
The effective date of this SOW is December 1, 2026.

2. Scope of Work
Jade Global will optimise and upgrade the Globex Salesforce Sales Cloud and CRM org: pipeline redesign, flow automation, reporting and release management. The work includes re-platforming of legacy custom objects and two integrations with the finance system.

3. Approach
Delivery follows Agile Scrum with two-week sprints and a sprint review at the end of each sprint.
The engagement runs for a duration of 3 months from the effective date.

4. Commercial Terms
The engagement is charged on a Time and Materials basis at the agreed rate card. Invoices are raised monthly in arrears.

5. Change Control
Scope changes are managed through written change requests. Effort variance up to 15% of the monthly plan can be absorbed without a change request.
"""

INITECH = """STATEMENT OF WORK
Initech HCM Managed Support Services
SOW-2026-0470 | Initech Solutions / Jade Global

1. Parties
This Statement of Work is between Initech Solutions ("Client") and Jade Global.
Start Date: November 1, 2026
End Date: October 31, 2027

2. Scope of Work
Jade Global will provide managed support and maintenance for the Initech Oracle HCM Cloud application, including incident support, problem management, quarterly release testing and minor enhancements.

3. Service Levels
Support is delivered under ITIL-aligned processes with SLA targets: P1 incidents responded to within 1 hour, P2 within 4 hours. Monthly SLA reports are provided.

4. Commercial Terms
Services are billed under a monthly Retainer of USD 38,000. Customer Reference: INI-HCM-7731.
Tolerance: ticket volume variance of 10% is covered by the retainer.
"""

KESTREL = """STATEMENT OF WORK
Kestrel Media Content Metadata Data Platform
SOW-2026-0475 | Kestrel Media Group / Jade Global

1. Parties
This SOW is made between Kestrel Media Group ("Client") and Jade Global. The project will commence on December 1, 2026.

2. Scope of Work
Jade Global will implement a unified content metadata Data Platform for Kestrel Media Group on a cloud data lakehouse, reconciling the ingest system, legacy catalogue database and rights management store. The scope includes data ingestion pipelines, a canonical metadata model, data quality rules, dashboards and knowledge transfer.

3. Approach
The work is delivered in Agile sprints with a product backlog owned by the Client. Sprint demos are held fortnightly.
The term of the engagement is 6 months.

4. Commercial Terms
The engagement is on a Time and Materials basis, billed monthly. The Client's Purchase Order No. KMG-PO-5521 must appear on all invoices.
Variance within a tolerance of 12% of the monthly plan does not require a change request.
"""

SOWS = {
    "SOW-ACME": ("SOW-2026-0457_Acme_Oracle_Fusion_Financials.txt", ACME),
    "SOW-GLOBEX": ("SOW-2026-0462_Globex_Salesforce_TM.txt", GLOBEX),
    "SOW-INITECH": ("SOW-2026-0470_Initech_HCM_Managed_Support.txt", INITECH),
    "SOW-KESTREL": ("SOW-2026-0475_Kestrel_Data_Platform.txt", KESTREL),
}
