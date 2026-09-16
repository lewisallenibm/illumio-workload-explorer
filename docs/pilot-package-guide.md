# Pilot package guide

This pilot is intended for a small test group. It runs locally on each
tester’s computer. It does not share data between testers and does not require
them to install PostgreSQL.

## What the package does

- On first launch, the app creates a private PostgreSQL workspace for that
  user only.
- It is bound to the local computer (`127.0.0.1`), not exposed as a network
  database or a Windows/macOS system service.
- Demo data is loaded only when the tester chooses the demo buttons in the
  Welcome tab.
- A tester's imported files and data remain only on their computer.
- Real PCE access remains separately guarded. PCE write-back is not enabled
  for this pilot.

## macOS tester steps

1. Download `Illumio-Workload-Explorer-0.1.0-macOS-pilot.zip`.
2. Double-click it to unzip, then move **Illumio Workload Explorer.app** to
   Applications if desired.
3. If macOS warns that the unsigned pilot cannot be opened, Control-click the
   app, choose **Open**, then choose **Open** once more.
4. Use the Welcome tab. For the demo, load mock Workloads, then mock CMDB,
   then run Reconciliation.

## Windows tester steps

1. Download `Illumio-Workload-Explorer-0.1.0-Windows-pilot.zip`.
2. Extract the entire ZIP to a normal writable folder, such as Documents. Do
   not run the executable from inside the ZIP.
3. Open **Illumio Workload Explorer.exe** from the extracted folder.
4. If Windows SmartScreen appears, use **More info** then **Run anyway** only
   after confirming the file came from the pilot share.
5. Use the Welcome tab for demo and import guidance.

## Remove only this app's local data

Quit the app first. The Welcome tab displays the exact command for the
current operating system. That command removes only the app-owned local
workspace; it does not touch PCE or any shared database.

## Build the Windows ZIP

Run the **Build Windows pilot package** workflow on GitHub. Provide the URL
of an official EDB Windows PostgreSQL binary ZIP when prompted. The official
PostgreSQL Windows page explicitly provides this kind of binary ZIP for
including PostgreSQL inside another application’s installer. Download the
completed workflow artifact and place it alongside the macOS ZIP in Box.
