import SwiftUI

struct MarkdownDocumentView: View {
  private let blocks: [MarkdownBlock]
  private let onOpenAnchor: (String) -> Void

  init(
    markdown: String,
    omittingTitle title: String? = nil,
    onOpenAnchor: @escaping (String) -> Void = { _ in }
  ) {
    var parsed = MarkdownParser.parse(markdown)
    if let title,
      let first = parsed.first,
      case .heading(let level, let text) = first,
      level == 1,
      text.trimmingCharacters(in: .whitespacesAndNewlines)
        == title.trimmingCharacters(in: .whitespacesAndNewlines)
    {
      parsed.removeFirst()
    }
    blocks = parsed
    self.onOpenAnchor = onOpenAnchor
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
        blockView(block)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .textSelection(.enabled)
    .environment(
      \.openURL,
      OpenURLAction { url in
        guard url.absoluteString.hasPrefix("#"), let fragment = url.fragment else {
          return .systemAction
        }
        onOpenAnchor(fragment)
        return .handled
      })
  }

  @ViewBuilder
  private func blockView(_ block: MarkdownBlock) -> some View {
    switch block {
    case .anchor(let identifier):
      Color.clear
        .frame(height: 0)
        .id(identifier)

    case .heading(let level, let text):
      InlineMarkdownText(text)
        .font(headingFont(level))
        .padding(.top, level <= 2 ? 12 : 6)

    case .paragraph(let text):
      InlineMarkdownText(text)
        .font(.body)
        .lineSpacing(5)

    case .blockquote(let text):
      HStack(alignment: .top, spacing: 12) {
        RoundedRectangle(cornerRadius: 2)
          .fill(Color.accentColor.opacity(0.7))
          .frame(width: 4)
        InlineMarkdownText(text)
          .font(.body)
          .foregroundStyle(.secondary)
          .lineSpacing(4)
      }
      .padding(.vertical, 4)
      .padding(.trailing, 12)

    case .unorderedList(let items):
      listView(items: items, ordered: false)

    case .orderedList(let items):
      listView(items: items, ordered: true)

    case .code(let language, let content):
      VStack(alignment: .leading, spacing: 6) {
        if let language {
          Text(language.uppercased())
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
        }
        ScrollView(.horizontal) {
          Text(content)
            .font(.system(.body, design: .monospaced))
            .textSelection(.enabled)
            .fixedSize(horizontal: true, vertical: true)
        }
      }
      .padding(12)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 8))

    case .table(let headers, let rows):
      MarkdownTableView(headers: headers, rows: rows)

    case .divider:
      Divider().padding(.vertical, 6)
    }
  }

  private func headingFont(_ level: Int) -> Font {
    switch level {
    case 1: .largeTitle.weight(.semibold)
    case 2: .title.weight(.semibold)
    case 3: .title2.weight(.semibold)
    case 4: .title3.weight(.semibold)
    case 5: .headline
    default: .subheadline.weight(.semibold)
    }
  }

  private func listView(items: [String], ordered: Bool) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      ForEach(Array(items.enumerated()), id: \.offset) { index, item in
        HStack(alignment: .firstTextBaseline, spacing: 9) {
          Text(ordered ? "\(index + 1)." : "•")
            .font(.body.weight(.medium))
            .foregroundStyle(.secondary)
            .frame(width: ordered ? 24 : 12, alignment: .trailing)
          InlineMarkdownText(item)
            .font(.body)
            .lineSpacing(3)
        }
      }
    }
    .padding(.leading, 4)
  }
}

private struct InlineMarkdownText: View {
  private let attributed: AttributedString

  init(_ source: String) {
    attributed =
      (try? AttributedString(
        markdown: source,
        options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
      )) ?? AttributedString(source)
  }

  var body: some View {
    Text(attributed)
      .fixedSize(horizontal: false, vertical: true)
  }
}

private struct MarkdownTableView: View {
  let headers: [String]
  let rows: [[String]]

  var body: some View {
    ScrollView(.horizontal) {
      Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
        GridRow {
          ForEach(Array(headers.enumerated()), id: \.offset) { _, header in
            cell(header, isHeader: true, isAlternate: false)
          }
        }
        ForEach(Array(rows.enumerated()), id: \.offset) { rowIndex, row in
          GridRow {
            ForEach(Array(row.enumerated()), id: \.offset) { _, value in
              cell(value, isHeader: false, isAlternate: rowIndex.isMultiple(of: 2))
            }
          }
        }
      }
      .overlay {
        RoundedRectangle(cornerRadius: 6)
          .stroke(.separator, lineWidth: 1)
      }
    }
  }

  private func cell(_ value: String, isHeader: Bool, isAlternate: Bool) -> some View {
    InlineMarkdownText(value)
      .font(isHeader ? .body.weight(.semibold) : .body)
      .padding(.horizontal, 10)
      .padding(.vertical, 8)
      .frame(minWidth: 120, maxWidth: 260, alignment: .leading)
      .background(
        isHeader
          ? Color.secondary.opacity(0.14)
          : (isAlternate ? Color.secondary.opacity(0.05) : Color.clear)
      )
  }
}
