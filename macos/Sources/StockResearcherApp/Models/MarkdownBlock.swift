import Foundation

enum MarkdownBlock: Equatable, Sendable {
  case anchor(String)
  case heading(level: Int, text: String)
  case paragraph(String)
  case blockquote(String)
  case unorderedList([String])
  case orderedList([String])
  case code(language: String?, content: String)
  case table(headers: [String], rows: [[String]])
  case divider
}

enum MarkdownParser {
  static func parse(_ markdown: String) -> [MarkdownBlock] {
    let lines = markdown.components(separatedBy: .newlines)
    var blocks: [MarkdownBlock] = []
    var paragraph: [String] = []
    var index = 0

    func flushParagraph() {
      guard !paragraph.isEmpty else { return }
      blocks.append(.paragraph(paragraph.joined(separator: " ")))
      paragraph.removeAll(keepingCapacity: true)
    }

    while index < lines.count {
      let line = lines[index]
      let trimmed = line.trimmingCharacters(in: .whitespaces)

      if trimmed.isEmpty {
        flushParagraph()
        index += 1
        continue
      }

      if let anchor = anchorID(from: trimmed) {
        flushParagraph()
        blocks.append(.anchor(anchor))
        index += 1
        continue
      }

      if trimmed.hasPrefix("```") {
        flushParagraph()
        let languageText = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
        let language = languageText.isEmpty ? nil : languageText
        index += 1
        var codeLines: [String] = []
        while index < lines.count
          && !lines[index].trimmingCharacters(in: .whitespaces).hasPrefix("```")
        {
          codeLines.append(lines[index])
          index += 1
        }
        if index < lines.count { index += 1 }
        blocks.append(.code(language: language, content: codeLines.joined(separator: "\n")))
        continue
      }

      if let heading = heading(from: trimmed) {
        flushParagraph()
        blocks.append(heading)
        index += 1
        continue
      }

      if isDivider(trimmed) {
        flushParagraph()
        blocks.append(.divider)
        index += 1
        continue
      }

      if index + 1 < lines.count,
        trimmed.contains("|"),
        isTableSeparator(lines[index + 1])
      {
        flushParagraph()
        let headers = tableCells(from: line)
        index += 2
        var rows: [[String]] = []
        while index < lines.count {
          let row = lines[index].trimmingCharacters(in: .whitespaces)
          guard !row.isEmpty, row.contains("|") else { break }
          rows.append(normalize(tableCells(from: lines[index]), count: headers.count))
          index += 1
        }
        blocks.append(.table(headers: headers, rows: rows))
        continue
      }

      if trimmed.hasPrefix(">") {
        flushParagraph()
        var quoteLines: [String] = []
        while index < lines.count {
          let quote = lines[index].trimmingCharacters(in: .whitespaces)
          guard quote.hasPrefix(">") else { break }
          quoteLines.append(String(quote.dropFirst()).trimmingCharacters(in: .whitespaces))
          index += 1
        }
        blocks.append(.blockquote(quoteLines.joined(separator: "\n")))
        continue
      }

      if unorderedItem(from: trimmed) != nil {
        flushParagraph()
        var items: [String] = []
        while index < lines.count,
          let item = unorderedItem(
            from: lines[index].trimmingCharacters(in: .whitespaces)
          )
        {
          items.append(item)
          index += 1
        }
        blocks.append(.unorderedList(items))
        continue
      }

      if orderedItem(from: trimmed) != nil {
        flushParagraph()
        var items: [String] = []
        while index < lines.count,
          let item = orderedItem(
            from: lines[index].trimmingCharacters(in: .whitespaces)
          )
        {
          items.append(item)
          index += 1
        }
        blocks.append(.orderedList(items))
        continue
      }

      paragraph.append(trimmed)
      index += 1
    }

    flushParagraph()
    return blocks
  }

  private static func heading(from line: String) -> MarkdownBlock? {
    let level = line.prefix(while: { $0 == "#" }).count
    guard (1...6).contains(level) else { return nil }
    let remainder = line.dropFirst(level)
    guard remainder.first == " " else { return nil }
    return .heading(
      level: level,
      text: remainder.trimmingCharacters(in: .whitespaces)
    )
  }

  private static func unorderedItem(from line: String) -> String? {
    guard line.count >= 2 else { return nil }
    let marker = line.first
    guard ["-", "*", "+"].contains(marker), line.dropFirst().first == " " else {
      return nil
    }
    return String(line.dropFirst(2)).trimmingCharacters(in: .whitespaces)
  }

  private static func orderedItem(from line: String) -> String? {
    guard let period = line.firstIndex(of: ".") else { return nil }
    let number = line[..<period]
    guard !number.isEmpty, number.allSatisfy(\.isNumber) else { return nil }
    let remainder = line[line.index(after: period)...]
    guard remainder.first == " " else { return nil }
    return remainder.trimmingCharacters(in: .whitespaces)
  }

  private static func isDivider(_ line: String) -> Bool {
    let compact = line.replacingOccurrences(of: " ", with: "")
    guard compact.count >= 3, let marker = compact.first, ["-", "_", "*"].contains(marker) else {
      return false
    }
    return compact.allSatisfy { $0 == marker }
  }

  private static func anchorID(from line: String) -> String? {
    guard line.hasPrefix("<a "), line.hasSuffix("</a>") else { return nil }
    for quote in ["\"", "'"] {
      let prefix = "id=\(quote)"
      guard let start = line.range(of: prefix) else { continue }
      let remainder = line[start.upperBound...]
      guard let end = remainder.firstIndex(of: Character(quote)) else { continue }
      let identifier = String(remainder[..<end])
      if !identifier.isEmpty { return identifier }
    }
    return nil
  }

  private static func isTableSeparator(_ line: String) -> Bool {
    let cells = tableCells(from: line)
    guard !cells.isEmpty else { return false }
    return cells.allSatisfy { cell in
      let marker = cell.trimmingCharacters(in: CharacterSet(charactersIn: ": "))
      return marker.count >= 3 && marker.allSatisfy { $0 == "-" }
    }
  }

  private static func tableCells(from line: String) -> [String] {
    var content = line.trimmingCharacters(in: .whitespaces)
    if content.hasPrefix("|") { content.removeFirst() }
    if content.hasSuffix("|") { content.removeLast() }
    return content.split(separator: "|", omittingEmptySubsequences: false).map {
      $0.trimmingCharacters(in: .whitespaces)
    }
  }

  private static func normalize(_ cells: [String], count: Int) -> [String] {
    if cells.count == count { return cells }
    if cells.count > count { return Array(cells.prefix(count)) }
    return cells + Array(repeating: "", count: count - cells.count)
  }
}
