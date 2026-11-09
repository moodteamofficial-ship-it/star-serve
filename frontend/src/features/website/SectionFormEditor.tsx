import {
  Field,
  FormSection,
  ImageField,
  ItemCard,
  LinkFields,
  SelectInput,
  TextArea,
  TextInput,
  Toggle,
} from "@/features/website/AdminFormFields";

type SectionFormEditorProps = {
  sectionType: string;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function moveItem<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(index, 1);
  next.splice(nextIndex, 0, item!);
  return next;
}

export function SectionFormEditor({ sectionType, value, onChange }: SectionFormEditorProps) {
  function patch(partial: Record<string, unknown>) {
    onChange({ ...value, ...partial });
  }

  if (sectionType === "hero") {
    return (
      <div className="website-form">
        <FormSection title="Message" description="What visitors read first.">
          <div className="website-field-grid">
            <Field label="Eyebrow">
              <TextInput
                value={str(value.eyebrow)}
                onChange={(eyebrow) => patch({ eyebrow })}
                placeholder="Digital Insurance"
              />
            </Field>
            <Field label="Headline">
              <TextInput
                value={str(value.headline)}
                onChange={(headline) => patch({ headline })}
                placeholder="Insurance, Just a Touch Away."
              />
            </Field>
            <Field label="Supporting text" className="website-field--span-2">
              <TextArea
                value={str(value.description)}
                onChange={(description) => patch({ description })}
                rows={4}
              />
            </Field>
          </div>
        </FormSection>
        <ImageField
          label="Hero photo"
          src={str(value.image_src)}
          alt={str(value.image_alt)}
          onSrcChange={(image_src) => patch({ image_src })}
          onAltChange={(image_alt) => patch({ image_alt })}
        />
        <LinkFields
          labelPrefix="Primary button"
          labelValue={str(value.primary_label)}
          kindValue={str(value.primary_kind, "quote")}
          valueValue={str(value.primary_value)}
          onLabelChange={(primary_label) => patch({ primary_label })}
          onKindChange={(primary_kind) => patch({ primary_kind })}
          onValueChange={(primary_value) => patch({ primary_value })}
        />
        <LinkFields
          labelPrefix="Secondary button"
          labelValue={str(value.secondary_label)}
          kindValue={str(value.secondary_kind, "internal")}
          valueValue={str(value.secondary_value)}
          onLabelChange={(secondary_label) => patch({ secondary_label })}
          onKindChange={(secondary_kind) => patch({ secondary_kind })}
          onValueChange={(secondary_value) => patch({ secondary_value })}
        />
      </div>
    );
  }

  if (sectionType === "service_grid") {
    const services = asArray(value.services).map((item) => asRecord(item));
    return (
      <div className="website-form">
        <FormSection title="Section copy">
          <div className="website-field-grid">
            <Field label="Headline">
              <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
            </Field>
            <Field label="Introduction" className="website-field--span-2">
              <TextArea
                value={str(value.description)}
                onChange={(description) => patch({ description })}
                rows={3}
              />
            </Field>
          </div>
        </FormSection>
        <FormSection title="Services">
          <div className="website-list-toolbar">
            <p className="website-field-hint">Add, reorder, or remove cover cards.</p>
            <button
              type="button"
              className="website-btn website-btn--ghost"
              onClick={() =>
                patch({
                  services: [...services, { slug: "", title: "", summary: "" }],
                })
              }
            >
              Add service
            </button>
          </div>
          <div className="website-item-list">
            {services.map((service, index) => (
              <ItemCard
                key={`service-${index}`}
                title={str(service.title) || `Service ${index + 1}`}
                canMoveUp={index > 0}
                canMoveDown={index < services.length - 1}
                onMoveUp={() => patch({ services: moveItem(services, index, -1) })}
                onMoveDown={() => patch({ services: moveItem(services, index, 1) })}
                onRemove={() => patch({ services: services.filter((_, i) => i !== index) })}
              >
                <div className="website-field-grid">
                  <Field label="Title">
                    <TextInput
                      value={str(service.title)}
                      onChange={(title) => {
                        const next = [...services];
                        next[index] = { ...service, title };
                        patch({ services: next });
                      }}
                    />
                  </Field>
                  <Field label="Product code">
                    <TextInput
                      value={str(service.slug)}
                      onChange={(slug) => {
                        const next = [...services];
                        next[index] = { ...service, slug };
                        patch({ services: next });
                      }}
                      placeholder="motor-insurance"
                    />
                  </Field>
                  <Field label="Summary" className="website-field--span-2">
                    <TextArea
                      value={str(service.summary)}
                      onChange={(summary) => {
                        const next = [...services];
                        next[index] = { ...service, summary };
                        patch({ services: next });
                      }}
                      rows={2}
                    />
                  </Field>
                </div>
              </ItemCard>
            ))}
          </div>
        </FormSection>
      </div>
    );
  }

  if (sectionType === "statistics") {
    const items = asArray(value.items).map((item) => asRecord(item));
    return (
      <div className="website-form">
        <Field label="Small label above the numbers">
          <TextInput value={str(value.eyebrow)} onChange={(eyebrow) => patch({ eyebrow })} />
        </Field>
        <div className="website-list-toolbar">
          <h3>Numbers</h3>
          <button
            type="button"
            className="website-btn website-btn--ghost"
            onClick={() =>
              patch({
                items: [...items, { label: "", value: "", verified: true }],
              })
            }
          >
            Add number
          </button>
        </div>
        <div className="website-item-list">
          {items.map((item, index) => (
            <ItemCard
              key={`stat-${index}`}
              title={str(item.label) || `Number ${index + 1}`}
              canMoveUp={index > 0}
              canMoveDown={index < items.length - 1}
              onMoveUp={() => patch({ items: moveItem(items, index, -1) })}
              onMoveDown={() => patch({ items: moveItem(items, index, 1) })}
              onRemove={() => patch({ items: items.filter((_, i) => i !== index) })}
            >
              <div className="website-field-grid">
                <Field label="Label">
                  <TextInput
                    value={str(item.label)}
                    onChange={(label) => {
                      const next = [...items];
                      next[index] = { ...item, label };
                      patch({ items: next });
                    }}
                  />
                </Field>
                <Field label="Value">
                  <TextInput
                    value={str(item.value)}
                    onChange={(val) => {
                      const next = [...items];
                      next[index] = { ...item, value: val };
                      patch({ items: next });
                    }}
                  />
                </Field>
              </div>
              <Toggle
                checked={item.verified !== false}
                onChange={(verified) => {
                  const next = [...items];
                  next[index] = { ...item, verified };
                  patch({ items: next });
                }}
                label="Verified and visible on the website"
              />
            </ItemCard>
          ))}
        </div>
      </div>
    );
  }

  if (sectionType === "benefits") {
    const items = asArray(value.items).map((item) => asRecord(item));
    return (
      <div className="website-form">
        <Field label="Section headline">
          <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
        </Field>
        <div className="website-list-toolbar">
          <h3>Benefit cards</h3>
          <button
            type="button"
            className="website-btn website-btn--ghost"
            onClick={() => patch({ items: [...items, { title: "", body: "" }] })}
          >
            Add benefit
          </button>
        </div>
        <div className="website-item-list">
          {items.map((item, index) => (
            <ItemCard
              key={`benefit-${index}`}
              title={str(item.title) || `Benefit ${index + 1}`}
              canMoveUp={index > 0}
              canMoveDown={index < items.length - 1}
              onMoveUp={() => patch({ items: moveItem(items, index, -1) })}
              onMoveDown={() => patch({ items: moveItem(items, index, 1) })}
              onRemove={() => patch({ items: items.filter((_, i) => i !== index) })}
            >
              <Field label="Title">
                <TextInput
                  value={str(item.title)}
                  onChange={(title) => {
                    const next = [...items];
                    next[index] = { ...item, title };
                    patch({ items: next });
                  }}
                />
              </Field>
              <Field label="Description">
                <TextArea
                  value={str(item.body)}
                  onChange={(body) => {
                    const next = [...items];
                    next[index] = { ...item, body };
                    patch({ items: next });
                  }}
                  rows={3}
                />
              </Field>
            </ItemCard>
          ))}
        </div>
      </div>
    );
  }

  if (sectionType === "agent_promotion") {
    const bullets = asArray(value.bullets).map((item) => str(item));
    return (
      <div className="website-form">
        <Field label="Headline">
          <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
        </Field>
        <Field label="Supporting text">
          <TextArea
            value={str(value.description)}
            onChange={(description) => patch({ description })}
            rows={3}
          />
        </Field>
        <div className="website-list-toolbar">
          <h3>Highlight points</h3>
          <button
            type="button"
            className="website-btn website-btn--ghost"
            onClick={() => patch({ bullets: [...bullets, ""] })}
          >
            Add point
          </button>
        </div>
        <div className="website-item-list">
          {bullets.map((bullet, index) => (
            <ItemCard
              key={`bullet-${index}`}
              title={`Point ${index + 1}`}
              canMoveUp={index > 0}
              canMoveDown={index < bullets.length - 1}
              onMoveUp={() => patch({ bullets: moveItem(bullets, index, -1) })}
              onMoveDown={() => patch({ bullets: moveItem(bullets, index, 1) })}
              onRemove={() => patch({ bullets: bullets.filter((_, i) => i !== index) })}
            >
              <Field label="Text">
                <TextInput
                  value={bullet}
                  onChange={(nextValue) => {
                    const next = [...bullets];
                    next[index] = nextValue;
                    patch({ bullets: next });
                  }}
                />
              </Field>
            </ItemCard>
          ))}
        </div>
        <LinkFields
          labelPrefix="Primary button"
          labelValue={str(value.primary_label)}
          kindValue={str(value.primary_kind, "agent_register")}
          valueValue={str(value.primary_value)}
          onLabelChange={(primary_label) => patch({ primary_label })}
          onKindChange={(primary_kind) => patch({ primary_kind })}
          onValueChange={(primary_value) => patch({ primary_value })}
        />
        <LinkFields
          labelPrefix="Secondary button"
          labelValue={str(value.secondary_label)}
          kindValue={str(value.secondary_kind, "agent_login")}
          valueValue={str(value.secondary_value)}
          onLabelChange={(secondary_label) => patch({ secondary_label })}
          onKindChange={(secondary_kind) => patch({ secondary_kind })}
          onValueChange={(secondary_value) => patch({ secondary_value })}
        />
      </div>
    );
  }

  if (sectionType === "cta") {
    return (
      <div className="website-form">
        <FormSection title="Message">
          <div className="website-field-grid">
            <Field label="Headline">
              <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
            </Field>
            <Field label="Supporting text" className="website-field--span-2">
              <TextArea
                value={str(value.description)}
                onChange={(description) => patch({ description })}
                rows={3}
              />
            </Field>
          </div>
        </FormSection>
        <LinkFields
          labelPrefix="Button"
          labelValue={str(value.primary_label)}
          kindValue={str(value.primary_kind, "quote")}
          valueValue={str(value.primary_value)}
          onLabelChange={(primary_label) => patch({ primary_label })}
          onKindChange={(primary_kind) => patch({ primary_kind })}
          onValueChange={(primary_value) => patch({ primary_value })}
        />
      </div>
    );
  }

  if (sectionType === "editorial") {
    return (
      <div className="website-form">
        <FormSection title="Story">
          <Field label="Headline">
            <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
          </Field>
          <Field label="Story text">
            <TextArea value={str(value.body)} onChange={(body) => patch({ body })} rows={8} />
          </Field>
        </FormSection>
      </div>
    );
  }

  if (sectionType === "editorial_image") {
    return (
      <div className="website-form">
        <FormSection title="Story">
          <div className="website-field-grid">
            <Field label="Photo placement">
              <SelectInput
                value={str(value.layout, "image_right")}
                onChange={(layout) => patch({ layout })}
                options={[
                  { value: "image_right", label: "Photo on the right" },
                  { value: "image_left", label: "Photo on the left" },
                ]}
              />
            </Field>
            <Field label="Eyebrow">
              <TextInput value={str(value.eyebrow)} onChange={(eyebrow) => patch({ eyebrow })} />
            </Field>
            <Field label="Headline" className="website-field--span-2">
              <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
            </Field>
            <Field label="Story text" className="website-field--span-2">
              <TextArea value={str(value.body)} onChange={(body) => patch({ body })} rows={5} />
            </Field>
          </div>
        </FormSection>
        <ImageField
          label="Section photo"
          src={str(value.image_src)}
          alt={str(value.image_alt)}
          onSrcChange={(image_src) => patch({ image_src })}
          onAltChange={(image_alt) => patch({ image_alt })}
        />
        <LinkFields
          labelPrefix="Button"
          labelValue={str(value.primary_label)}
          kindValue={str(value.primary_kind, "internal")}
          valueValue={str(value.primary_value)}
          onLabelChange={(primary_label) => patch({ primary_label })}
          onKindChange={(primary_kind) => patch({ primary_kind })}
          onValueChange={(primary_value) => patch({ primary_value })}
        />
      </div>
    );
  }

  if (sectionType === "contact_strip") {
    return (
      <div className="website-form">
        <FormSection title="Contact details">
          <div className="website-field-grid">
            <Field label="Location">
              <TextInput value={str(value.location)} onChange={(location) => patch({ location })} />
            </Field>
            <Field label="Email">
              <TextInput value={str(value.email)} onChange={(email) => patch({ email })} />
            </Field>
            <Field label="Phone">
              <TextInput value={str(value.phone)} onChange={(phone) => patch({ phone })} />
            </Field>
          </div>
        </FormSection>
      </div>
    );
  }

  if (sectionType === "faq") {
    const items = asArray(value.items).map((item) => asRecord(item));
    return (
      <div className="website-form">
        <Field label="Section headline">
          <TextInput value={str(value.headline)} onChange={(headline) => patch({ headline })} />
        </Field>
        <div className="website-list-toolbar">
          <h3>Questions</h3>
          <button
            type="button"
            className="website-btn website-btn--ghost"
            onClick={() => patch({ items: [...items, { question: "", answer: "" }] })}
          >
            Add question
          </button>
        </div>
        <div className="website-item-list">
          {items.map((item, index) => (
            <ItemCard
              key={`faq-${index}`}
              title={str(item.question) || `Question ${index + 1}`}
              canMoveUp={index > 0}
              canMoveDown={index < items.length - 1}
              onMoveUp={() => patch({ items: moveItem(items, index, -1) })}
              onMoveDown={() => patch({ items: moveItem(items, index, 1) })}
              onRemove={() => patch({ items: items.filter((_, i) => i !== index) })}
            >
              <Field label="Question">
                <TextInput
                  value={str(item.question)}
                  onChange={(question) => {
                    const next = [...items];
                    next[index] = { ...item, question };
                    patch({ items: next });
                  }}
                />
              </Field>
              <Field label="Answer">
                <TextArea
                  value={str(item.answer)}
                  onChange={(answer) => {
                    const next = [...items];
                    next[index] = { ...item, answer };
                    patch({ items: next });
                  }}
                  rows={3}
                />
              </Field>
            </ItemCard>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="website-form">
      <p className="website-admin-muted">
        This section type does not have a guided form yet. Contact your technical team if you need
        changes here.
      </p>
    </div>
  );
}

export function supportsGuidedForm(sectionType: string): boolean {
  return [
    "hero",
    "service_grid",
    "statistics",
    "benefits",
    "agent_promotion",
    "cta",
    "editorial",
    "editorial_image",
    "contact_strip",
    "faq",
  ].includes(sectionType);
}
