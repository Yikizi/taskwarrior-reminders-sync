import Foundation
import EventKit
import CoreLocation

// MARK: - Configuration

let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
let projectDir = "\(homeDir)/taskwarrior-reminders-sync"
let pythonPath = "\(projectDir)/.venv/bin/python"
let syncModule = "tw_reminders.sync_from_reminders"

// MARK: - Reminder JSON Model

struct ReminderJSON: Codable {
    let identifier: String
    let title: String
    let notes: String?
    let isCompleted: Bool
    let priority: Int
    let dueDate: String?
    let completionDate: String?
    let list: String
    let hasLocation: Bool
    let locationName: String?
    let locationLatitude: Double?
    let locationLongitude: Double?
    let locationRadius: Double?
    let modificationDate: String?
}

// MARK: - Date Formatting

let isoFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

func formatDate(_ date: Date?) -> String? {
    guard let date = date else { return nil }
    return isoFormatter.string(from: date)
}

// MARK: - EventKit Helpers

let store = EKEventStore()

func requestAccess() -> Bool {
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false

    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { success, error in
            granted = success
            if let error = error {
                fputs("Error requesting access: \(error.localizedDescription)\n", stderr)
            }
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { success, error in
            granted = success
            semaphore.signal()
        }
    }

    semaphore.wait()
    return granted
}

func fetchAllReminders() -> [EKReminder] {
    let semaphore = DispatchSemaphore(value: 0)
    var reminders: [EKReminder] = []

    let predicate = store.predicateForReminders(in: nil)
    store.fetchReminders(matching: predicate) { result in
        reminders = result ?? []
        semaphore.signal()
    }

    semaphore.wait()
    return reminders
}

func getLocationAlarm(_ reminder: EKReminder) -> EKAlarm? {
    return reminder.alarms?.first { $0.structuredLocation != nil }
}

func reminderToJSON(_ reminder: EKReminder) -> ReminderJSON {
    let locationAlarm = getLocationAlarm(reminder)
    let location = locationAlarm?.structuredLocation
    let geofence = location?.geoLocation

    return ReminderJSON(
        identifier: reminder.calendarItemIdentifier,
        title: reminder.title ?? "",
        notes: reminder.notes,
        isCompleted: reminder.isCompleted,
        priority: reminder.priority,
        dueDate: formatDate(reminder.dueDateComponents?.date),
        completionDate: formatDate(reminder.completionDate),
        list: reminder.calendar.title,
        hasLocation: location != nil,
        locationName: location?.title,
        locationLatitude: geofence?.coordinate.latitude,
        locationLongitude: geofence?.coordinate.longitude,
        locationRadius: location?.radius,
        modificationDate: formatDate(reminder.lastModifiedDate)
    )
}

// MARK: - Commands

func exportReminders(pendingOnly: Bool = false, locationOnly: Bool = false) {
    guard requestAccess() else {
        fputs("Error: Reminders access denied\n", stderr)
        exit(1)
    }

    var reminders = fetchAllReminders()

    if pendingOnly {
        reminders = reminders.filter { !$0.isCompleted }
    }

    if locationOnly {
        reminders = reminders.filter { getLocationAlarm($0) != nil }
    }

    let jsonReminders = reminders.map { reminderToJSON($0) }

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

    do {
        let data = try encoder.encode(jsonReminders)
        if let json = String(data: data, encoding: .utf8) {
            print(json)
        }
    } catch {
        fputs("Error encoding JSON: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

func exportLocations() {
    guard requestAccess() else {
        fputs("Error: Reminders access denied\n", stderr)
        exit(1)
    }

    let reminders = fetchAllReminders().filter { getLocationAlarm($0) != nil }

    // Extract unique locations
    var locations: [[String: Any]] = []
    var seenNames = Set<String>()

    for reminder in reminders {
        guard let alarm = getLocationAlarm(reminder),
              let location = alarm.structuredLocation,
              let name = location.title,
              !seenNames.contains(name) else { continue }

        seenNames.insert(name)

        var loc: [String: Any] = ["name": name]
        if let geo = location.geoLocation {
            loc["latitude"] = geo.coordinate.latitude
            loc["longitude"] = geo.coordinate.longitude
            loc["radius"] = location.radius > 0 ? location.radius : 100
        }
        locations.append(loc)
    }

    do {
        let data = try JSONSerialization.data(withJSONObject: ["locations": locations], options: [.prettyPrinted, .sortedKeys])
        if let json = String(data: data, encoding: .utf8) {
            print(json)
        }
    } catch {
        fputs("Error encoding JSON: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

func startListener() {
    guard requestAccess() else {
        fputs("Error: Reminders access denied\n", stderr)
        exit(1)
    }

    fputs("Listening for Reminders changes...\n", stderr)

    // Listen for changes (event-driven, no polling)
    NotificationCenter.default.addObserver(
        forName: .EKEventStoreChanged,
        object: store,
        queue: .main
    ) { _ in
        fputs("[\(Date())] Reminders changed, triggering sync...\n", stderr)
        triggerSync()
    }

    // Keep alive (uses zero CPU while waiting)
    RunLoop.main.run()
}

func triggerSync() {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: pythonPath)
    task.arguments = ["-m", syncModule]
    task.currentDirectoryURL = URL(fileURLWithPath: projectDir + "/src")

    do {
        try task.run()
    } catch {
        fputs("Error running sync: \(error.localizedDescription)\n", stderr)
    }
}

// MARK: - Main

// MARK: - Create/Update/Delete

func createReminder(json: String) {
    guard requestAccess() else {
        fputs("{\"error\": \"Reminders access denied\"}\n", stderr)
        exit(1)
    }

    guard let data = json.data(using: .utf8),
          let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        fputs("{\"error\": \"Invalid JSON\"}\n", stderr)
        exit(1)
    }

    let reminder = EKReminder(eventStore: store)
    reminder.title = dict["title"] as? String ?? "Untitled"

    // Set list/calendar
    if let listName = dict["list"] as? String {
        let calendars = store.calendars(for: .reminder)
        if let calendar = calendars.first(where: { $0.title == listName }) {
            reminder.calendar = calendar
        } else {
            reminder.calendar = store.defaultCalendarForNewReminders()
        }
    } else {
        reminder.calendar = store.defaultCalendarForNewReminders()
    }

    // Set priority (1=high, 5=medium, 9=low)
    if let priority = dict["priority"] as? Int {
        reminder.priority = priority
    }

    // Set notes
    if let notes = dict["notes"] as? String {
        reminder.notes = notes
    }

    // Set due date
    if let dueDateStr = dict["due_date"] as? String {
        if let dueDate = parseDate(dueDateStr) {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: dueDate
            )
            // Add time-based alarm
            let alarm = EKAlarm(absoluteDate: dueDate)
            reminder.addAlarm(alarm)
        }
    }

    // Set location alarm if provided
    if let locationName = dict["location_name"] as? String,
       let lat = dict["location_lat"] as? Double,
       let lon = dict["location_lon"] as? Double {
        let location = EKStructuredLocation(title: locationName)
        location.geoLocation = CLLocation(latitude: lat, longitude: lon)
        location.radius = dict["location_radius"] as? Double ?? 100

        let alarm = EKAlarm()
        alarm.structuredLocation = location
        let trigger = dict["location_trigger"] as? String ?? "arriving"
        alarm.proximity = trigger == "leaving" ? .leave : .enter
        reminder.addAlarm(alarm)
    }

    do {
        try store.save(reminder, commit: true)
        let result: [String: Any] = [
            "status": "created",
            "identifier": reminder.calendarItemIdentifier
        ]
        if let jsonData = try? JSONSerialization.data(withJSONObject: result),
           let jsonStr = String(data: jsonData, encoding: .utf8) {
            print(jsonStr)
        }
    } catch {
        fputs("{\"error\": \"\(error.localizedDescription)\"}\n", stderr)
        exit(1)
    }
}

func updateReminder(json: String) {
    guard requestAccess() else {
        fputs("{\"error\": \"Reminders access denied\"}\n", stderr)
        exit(1)
    }

    guard let data = json.data(using: .utf8),
          let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let identifier = dict["identifier"] as? String else {
        fputs("{\"error\": \"Invalid JSON or missing identifier\"}\n", stderr)
        exit(1)
    }

    guard let reminder = store.calendarItem(withIdentifier: identifier) as? EKReminder else {
        fputs("{\"error\": \"Reminder not found\"}\n", stderr)
        exit(1)
    }

    // Update fields if provided
    if let title = dict["title"] as? String {
        reminder.title = title
    }

    if let priority = dict["priority"] as? Int {
        reminder.priority = priority
    }

    if let notes = dict["notes"] as? String {
        reminder.notes = notes
    }

    if let isCompleted = dict["is_completed"] as? Bool {
        reminder.isCompleted = isCompleted
        if isCompleted {
            reminder.completionDate = Date()
        }
    }

    if let dueDateStr = dict["due_date"] as? String {
        if let dueDate = parseDate(dueDateStr) {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: dueDate
            )
        }
    }

    do {
        try store.save(reminder, commit: true)
        print("{\"status\": \"updated\"}")
    } catch {
        fputs("{\"error\": \"\(error.localizedDescription)\"}\n", stderr)
        exit(1)
    }
}

func deleteReminder(identifier: String) {
    guard requestAccess() else {
        fputs("{\"error\": \"Reminders access denied\"}\n", stderr)
        exit(1)
    }

    guard let reminder = store.calendarItem(withIdentifier: identifier) as? EKReminder else {
        fputs("{\"error\": \"Reminder not found\"}\n", stderr)
        exit(1)
    }

    do {
        try store.remove(reminder, commit: true)
        print("{\"status\": \"deleted\"}")
    } catch {
        fputs("{\"error\": \"\(error.localizedDescription)\"}\n", stderr)
        exit(1)
    }
}

func parseDate(_ str: String) -> Date? {
    let formatters = [
        ISO8601DateFormatter(),
    ]
    for formatter in formatters {
        if let date = formatter.date(from: str) {
            return date
        }
    }
    // Try basic format
    let df = DateFormatter()
    df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    return df.date(from: str)
}

func printUsage() {
    let usage = """
    Usage: tw-reminders-listener <command> [options]

    Commands:
      listen              Start listening for Reminders changes (daemon mode)
      export              Export reminders as JSON to stdout
      export-locations    Export unique locations from location-based reminders
      create <json>       Create a reminder from JSON
      update <json>       Update a reminder (requires identifier in JSON)
      delete <identifier> Delete a reminder by identifier
      help                Show this help message

    Export options:
      --pending-only      Only export incomplete reminders
      --with-location     Only export reminders with location

    Create JSON format:
      {"title": "...", "list": "...", "priority": 5, "due_date": "ISO8601", "notes": "..."}
      Optional location: {"location_name": "...", "location_lat": 59.4, "location_lon": 24.7}

    Examples:
      tw-reminders-listener export --pending-only
      tw-reminders-listener create '{"title": "Buy milk", "list": "Groceries"}'
      tw-reminders-listener delete "ABC123-DEF456"
    """
    print(usage)
}

let args = Array(CommandLine.arguments.dropFirst())

guard let command = args.first else {
    printUsage()
    exit(0)
}

let restArgs = Array(args.dropFirst())
let flags = Set(restArgs.filter { $0.hasPrefix("--") })
let positionalArgs = restArgs.filter { !$0.hasPrefix("--") }

switch command {
case "listen":
    startListener()
case "export":
    let pendingOnly = flags.contains("--pending-only")
    let locationOnly = flags.contains("--with-location")
    exportReminders(pendingOnly: pendingOnly, locationOnly: locationOnly)
case "export-locations":
    exportLocations()
case "create":
    guard let json = positionalArgs.first else {
        fputs("Error: create requires JSON argument\n", stderr)
        exit(1)
    }
    createReminder(json: json)
case "update":
    guard let json = positionalArgs.first else {
        fputs("Error: update requires JSON argument\n", stderr)
        exit(1)
    }
    updateReminder(json: json)
case "delete":
    guard let identifier = positionalArgs.first else {
        fputs("Error: delete requires identifier argument\n", stderr)
        exit(1)
    }
    deleteReminder(identifier: identifier)
case "help", "--help", "-h":
    printUsage()
default:
    fputs("Unknown command: \(command)\n", stderr)
    printUsage()
    exit(1)
}
