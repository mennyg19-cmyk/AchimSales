var HELP = {

    /* ===== Reports page — what each report does ===== */

    "report-ordered": {
        title: "Ordered Report",
        body: "Shows all orders placed during the time period you choose.<br><br>" +
              "You'll get a breakdown by customer, by item, by order, and by salesman. " +
              "You can also choose to see only open orders (ones that haven't shipped or been cancelled yet).<br><br>" +
              "<strong>Tip:</strong> If you pick \"Open Orders Only\", the time period is ignored and it shows all open orders regardless of when they were placed."
    },

    "report-invoiced": {
        title: "Invoiced Report",
        body: "Shows everything that was shipped and billed during the time period you choose.<br><br>" +
              "Includes a summary by customer, full invoice details, any credits, and commission information.<br><br>" +
              "You can narrow it down to specific customers if needed."
    },

    "report-salesman": {
        title: "Salesman Report",
        body: "Compares each salesman's sales numbers month by month for the year you pick.<br><br>" +
              "Shows how much was sold this month vs. last month, and year-to-date totals compared to last year.<br><br>" +
              "Just pick the year and tap Run — no other options needed."
    },

    "report-number_4": {
        title: "Number 4 Report",
        body: "Shows sold quantities (and dollars on By Customer) for each month, grouped by item.<br><br>" +
              "Each view has two tabs: rolling 12 months, and year to date. By Item is quantities only — no dollar columns. By Customer keeps monthly dollars, totals, average price, and book price.<br><br>" +
              "Pick By Customer, By Item, or Both. Both shows all four tabs."
    },

    "param-n4-mode": {
        title: "View",
        body: "How to organize the rows.<br><br>" +
              "<b>By Customer</b> — customer + item rows with dollars; two tabs (12 months and YTD).<br>" +
              "<b>By Item</b> — the same rows with items first, quantities only; two tabs (12 months and YTD).<br>" +
              "<b>Both</b> — all four tabs. Rows start grouped by item."
    },

    "report-customer_activity": {
        title: "Customer Activity Report",
        body: "Shows when each customer last placed an order, organized by salesman.<br><br>" +
              "Helps you spot customers who haven't ordered in a while.<br><br>" +
              "Tabs: <strong>All</strong> (every customer with a Salesman column), " +
              "one tab per salesman, then Unassigned.<br><br>" +
              "There are no options to set — just tap Run."
    },

    "report-item_averages": {
        title: "Item Averages",
        body: "Company-wide quantity averages from the Number 4 By Item view.<br><br>" +
              "One row per item with 12-month quantity, average per month, and average per week."
    },

    "report-sales_by_state": {
        title: "Sales by State",
        body: "Shows invoiced sales by ship-to state for the year you pick.<br><br>" +
              "<strong>Summary</strong> — one row per state with sales dollars. New York City dollars sit in their own column when the state has them.<br>" +
              "<strong>New York City</strong> — invoice lines classified as New York City.<br>" +
              "<strong>Detail</strong> — every known-state invoice in the year, with ship-to address.<br><br>" +
              "Keep negative amounts. Unknown locations are not mixed into a state row.<br><br>" +
              "Pick the year and tap Run."
    },

    "report-customer_aging": {
        title: "Customer Aging Report",
        body: "Shows how much each customer owes and how old the balances are.<br><br>" +
              "The master report has tabs for All Customers, DS, WH, MISC, and a separate tab for each salesman.<br><br>" +
              "Columns include: Customer #, Name, Group, Salesman, Amount Due, Last Payment Date, Last Payment Amount, Number of Open Invoices, and aging buckets (Current, 30, 60, 90, 91+ days).<br><br>" +
              "You can filter by salesman or by specific customers. Automated reports are emailed to each salesman with just their customers."
    },

    /* ===== Report form — parameter help ===== */

    "param-period": {
        title: "Time Period",
        body: "This controls which dates the report covers:<br><br>" +
              "<strong>Yesterday</strong> — just yesterday's activity.<br>" +
              "<strong>Last 7 Days</strong> — the past week.<br>" +
              "<strong>This Month</strong> — from the 1st of this month until today.<br>" +
              "<strong>Last Month</strong> — the full previous calendar month (1st through last day). Useful for monthly schedules that fire on the 1st.<br>" +
              "<strong>Year to Date</strong> — from January 1st until today.<br>" +
              "<strong>Custom Range</strong> — you pick the exact start and end dates.<br><br>" +
              "<strong>Important:</strong> On the Ordered Report, if you pick \"Open Orders Only\", the time period is ignored — it will show all open orders no matter when they were placed."
    },

    "param-custom-dates": {
        title: "Custom Date Range",
        body: "Pick a start date (From) and an end date (To).<br><br>" +
              "The report will include everything between those two dates. Both dates are included."
    },

    "param-status": {
        title: "Order Status",
        body: "<strong>All Orders</strong> — shows everything: open, shipped, and cancelled orders for the time period you picked.<br><br>" +
              "<strong>Open Orders Only</strong> — shows only orders that haven't been fully shipped or cancelled yet. " +
              "When you pick this, the time period is ignored and it shows <em>all</em> open orders regardless of when they were placed.<br><br>" +
              "The report will include a summary by customer, a breakdown by item, and a list of each order."
    },

    "param-salesman": {
        title: "Salesman",
        body: "Pick a specific salesman to see only their orders or invoices.<br><br>" +
              "If you leave it on \"All Salesmen\", the report will include everyone.<br><br>" +
              "<strong>What happens behind the scenes:</strong><br>" +
              "When you pick a specific salesman, the report is filtered to only show that salesman's data. " +
              "The output will include a summary, customer breakdown, item breakdown, and order details — but no \"By Salesman\" tab since it's already filtered to one person."
    },

    "param-customers": {
        title: "Customers",
        body: "Search for customers by name or account number, then tap to add them.<br><br>" +
              "You can add as many customers as you want. Each one you pick will appear as a blue tag above the search box. Tap the X on a tag to remove it.<br><br>" +
              "If you don't pick any customers, the report includes all of them."
    },

    "param-year": {
        title: "Report Year",
        body: "Pick the calendar year the report covers. It defaults to this year.<br><br>" +
              "On Sales by State that is the invoice year (January 1 through December 31).<br><br>" +
              "On the Salesman Report it also compares that year to the previous year, month by month."
    },

    "param-save-preset": {
        title: "Save as Preset",
        body: "A preset saves the report and all the options you've picked so you can run it again with one tap.<br><br>" +
              "After saving, your preset will appear on the Reports page as a card. Just tap \"Run\" on it and the report will start automatically with the same settings.<br><br>" +
              "Give it a name you'll remember, like \"My Daily Orders\" or \"Monthly Invoiced\"."
    },

    "param-background": {
        title: "Run in Background",
        body: "If the report is taking a while, tap this to keep it running in the background.<br><br>" +
              "You'll be free to use the app while it finishes. When it's done, you'll get a notification and you can find the report in your History."
    },

    /* ===== Dashboard ===== */

    "dashboard-cards": {
        title: "Dashboard Overview",
        body: "This page shows how your customers are doing based on their ordering patterns.<br><br>" +
              "<strong>Total Customers</strong> — everyone assigned to you.<br>" +
              "<strong>New</strong> — customers who have only ordered once since we moved to the new system.<br>" +
              "<strong>Active</strong> — customers who are ordering on their normal schedule.<br>" +
              "<strong>Overdue</strong> — customers who are taking longer than usual to place their next order.<br>" +
              "<strong>Inactive</strong> — customers who haven't ordered in over a year.<br><br>" +
              "Tap any card to show only that group in the table below. Tap the <strong>?</strong> in any tile for a more detailed explanation.<br><br>" +
              "The table columns:<br>" +
              "<strong>Avg Freq</strong> — the average number of days between this customer's orders.<br>" +
              "<strong>Threshold</strong> — how many days we wait before marking them overdue (based on their ordering pattern plus some buffer)."
    },

    "dashboard-tile-total": {
        title: "Total Customers",
        body: "Every customer assigned to you (or to the salesman you're viewing).<br><br>" +
              "Tap this tile to clear any filter and show everyone in the table below."
    },

    "dashboard-tile-new": {
        title: "New",
        body: "Customers who have only placed one order since the move to D365.<br><br>" +
              "We need at least 2 orders to figure out how often a customer normally orders, so 'New' customers don't yet have an Avg Freq or Threshold." +
              " Once they place their second order, they'll move to Active, Overdue, or Inactive."
    },

    "dashboard-tile-active": {
        title: "Active",
        body: "Customers who are ordering on their normal schedule.<br><br>" +
              "We look at the gap between each of their past orders to figure out their typical ordering frequency." +
              " As long as it's been less time since their last order than that frequency (plus a small buffer), they're Active."
    },

    "dashboard-tile-overdue": {
        title: "Overdue",
        body: "Customers who are taking longer than usual to place their next order.<br><br>" +
              "Once it's been more time since their last order than their typical frequency (plus the buffer), they show up here." +
              " These are the customers worth a phone call."
    },

    "dashboard-tile-inactive": {
        title: "Inactive (1+ year)",
        body: "Customers who haven't placed an order in over a year.<br><br>" +
              "They're probably not coming back without a serious push. We separate them from Overdue so they don't drown out the more time-sensitive Overdue customers."
    },

    "dashboard-avg-freq": {
        title: "Average Frequency",
        body: "The average number of days between this customer's orders.<br><br>" +
              "For example, if a customer usually orders every 30 days, this will show 30."
    },

    "dashboard-threshold": {
        title: "Threshold",
        body: "The number of days we wait before considering a customer \"overdue\".<br><br>" +
              "It's based on each customer's average ordering frequency plus some extra buffer. If they go past this number of days without ordering, they'll show up as Overdue."
    },

    "dashboard-refresh": {
        title: "Refresh Data",
        body: "Tap this to pull the latest customer and order information from D365.<br><br>" +
              "This can take a few minutes. You'll see a progress bar while it's working. Once it's done, the page will update with the newest data.<br><br>" +
              "Data also refreshes automatically every 4 hours in the background."
    },

    "dashboard-include": {
        title: "Include in Dashboard",
        body: "When this is turned on, this customer counts toward your dashboard numbers (Active, Overdue, Inactive) and can trigger notifications.<br><br>" +
              "Turn it off to exclude this customer from your dashboard. This is useful for customers you don't need to track, like internal accounts or one-time buyers."
    },

    /* ===== Settings ===== */

    "settings-exclusions": {
        title: "Customer Exclusions",
        body: "This lets you hide certain customers from your dashboard.<br><br>" +
              "Excluded customers won't count toward your totals, won't show up as overdue, and won't trigger any notifications.<br><br>" +
              "Toggle a customer off to exclude them. Don't forget to tap Save when you're done."
    },

    "settings-feature-flags": {
        title: "Feature Flags",
        body: "These are on/off switches for app features.<br><br>" +
              "Turning a flag off will disable that feature for everyone. This is mainly used for testing new features or temporarily disabling something."
    },

    "settings-report-visibility": {
        title: "Report Visibility",
        body: "This controls which reports are available in the app.<br><br>" +
              "If you turn a report off here, nobody will see it on the Reports page (unless they have a special override). Turn it back on to make it available again."
    },

    "settings-active-dropdowns": {
        title: "Active in Dropdowns",
        body: "When this is on, this user will appear in salesman dropdowns throughout the app (like when picking a salesman on a report).<br><br>" +
              "Turn it off for users who have left or shouldn't appear as a selectable option anymore."
    },

    "settings-dashboard-access": {
        title: "Dashboard Access",
        body: "When this is on, this user can see the Dashboard tab and view customer activity information.<br><br>" +
              "Turn it off if this user doesn't need to see dashboard data."
    },

    "settings-test-access": {
        title: "Test-Site Access",
        body: "When this is on, this user sees a link to the legacy test site.<br><br>" +
              "Only matters when the global Test-Site feature flag is also on."
    },

    "settings-assigned-salesmen": {
        title: "Assigned Salesmen",
        body: "For managers and non-privileged users, this limits which salesmen's customers and orders they can see.<br><br>" +
              "Admins and developers always see every salesman regardless of this setting."
    },

    "settings-external-user": {
        title: "External Login (magic link)",
        body: "Use this for sales reps outside Achim who don't have a Microsoft account on our tenant.<br><br>" +
              "When checked, the user signs in by entering their email on the login page; we send them a one-time link from <strong>reports@achimonline.com</strong>. The link expires in 15 minutes and works once.<br><br>" +
              "Internal Achim staff should leave this unchecked &mdash; they sign in with Microsoft."
    },

    /* ===== Schedules ===== */

    "schedules-sync": {
        title: "Sync from Azure",
        body: "This pulls in all the report schedules that are currently set up in Azure (where the automated reports run).<br><br>" +
              "Use this to see what's currently scheduled, or to refresh the list after someone makes changes directly in Azure."
    },

    "schedules-frequency": {
        title: "Frequency & Interval",
        body: "<strong>Frequency</strong> is how often the report runs: Daily, Weekly, Monthly, or just One Time.<br><br>" +
              "<strong>Interval</strong> is how many to skip. For example, if you set Weekly with interval 2, it runs every other week. Daily with interval 1 means every day.<br><br>" +
              "For <strong>Weekly</strong>, you can pick which days of the week it should run on.<br><br>" +
              "For <strong>Monthly</strong>, you pick which day(s) of the month. You can select multiple days (e.g., the 1st and 15th). " +
              "There's also a <em>Last day of the month</em> option — this automatically runs on the final day whether it's the 28th, 29th, 30th, or 31st."
    },

    "schedules-email": {
        title: "Send Email",
        body: "When this is checked, the report will be emailed to the usual recipients after it finishes running.<br><br>" +
              "If it's unchecked, the report will still be generated and saved to the shared folder, but no email will be sent."
    },

    "schedules-customer": {
        title: "Customer (Schedules)",
        body: "Type in the customer account numbers you want the scheduled report to cover.<br><br>" +
              "Separate multiple customers with spaces. For example: <strong>9300 9301</strong><br><br>" +
              "If you leave this empty, the report will include all customers."
    },

    "schedules-salesman": {
        title: "Salesman (Schedules)",
        body: "Type in the salesman keys you want the scheduled report to run for.<br><br>" +
              "Separate multiple salesmen with spaces. Type <strong>all</strong> to run for every salesman — this will generate a separate report for each salesman and email it to them individually.<br><br>" +
              "If you leave this empty, the report runs for everyone combined into one file."
    },

    /* ===== History ===== */

    "history-statuses": {
        title: "Report Status",
        body: "Each report in your history has a status:<br><br>" +
              "<strong>Completed</strong> — the report finished successfully. You can view it here or download the Excel file.<br>" +
              "<strong>Running</strong> — the report is still being generated. Check back in a moment.<br>" +
              "<strong>No Data</strong> — the report ran but there was nothing to show for the time period and options you picked. Try a wider date range.<br>" +
              "<strong>Failed</strong> — something went wrong. You can tap Retry to try again, or try different options."
    }
};
