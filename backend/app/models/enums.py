import enum


class WorkspaceRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    APPROVER = "APPROVER"
    VIEWER = "VIEWER"


class TelegramAccountStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    TWO_FA_REQUIRED = "TWO_FA_REQUIRED"
    FLOOD_WAIT = "FLOOD_WAIT"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class ChannelHealth(str, enum.Enum):
    HEALTHY = "HEALTHY"
    NO_POST_PERMISSION = "NO_POST_PERMISSION"
    ACCOUNT_OFFLINE = "ACCOUNT_OFFLINE"
    FLOOD_WAIT = "FLOOD_WAIT"
    UNAVAILABLE = "UNAVAILABLE"


class ChannelSetMode(str, enum.Enum):
    EXACT = "EXACT"
    CTA_PER_CHANNEL = "CTA_PER_CHANNEL"
    CONTACT_PER_CHANNEL = "CONTACT_PER_CHANNEL"
    ADAPTED = "ADAPTED"


class ContentStatus(str, enum.Enum):
    IDEA = "IDEA"
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PARTIALLY_PUBLISHED = "PARTIALLY_PUBLISHED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


CONTENT_TRANSITIONS: dict[ContentStatus, set[ContentStatus]] = {
    ContentStatus.IDEA: {ContentStatus.DRAFT, ContentStatus.GENERATING, ContentStatus.ARCHIVED},
    ContentStatus.DRAFT: {
        ContentStatus.GENERATING,
        ContentStatus.PENDING_APPROVAL,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.GENERATING: {ContentStatus.DRAFT, ContentStatus.PENDING_APPROVAL, ContentStatus.FAILED},
    ContentStatus.PENDING_APPROVAL: {
        ContentStatus.APPROVED,
        ContentStatus.REJECTED,
        ContentStatus.DRAFT,
    },
    ContentStatus.APPROVED: {ContentStatus.SCHEDULED, ContentStatus.PUBLISHING, ContentStatus.DRAFT},
    ContentStatus.SCHEDULED: {ContentStatus.PUBLISHING, ContentStatus.APPROVED, ContentStatus.ARCHIVED},
    ContentStatus.PUBLISHING: {
        ContentStatus.PUBLISHED,
        ContentStatus.PARTIALLY_PUBLISHED,
        ContentStatus.FAILED,
    },
    ContentStatus.PUBLISHED: {ContentStatus.ARCHIVED},
    ContentStatus.PARTIALLY_PUBLISHED: {ContentStatus.PUBLISHING, ContentStatus.ARCHIVED},
    ContentStatus.FAILED: {
        ContentStatus.DRAFT,
        ContentStatus.GENERATING,  # retry of a failed generation
        ContentStatus.PUBLISHING,  # retry of a failed distribution
        ContentStatus.ARCHIVED,
    },
    ContentStatus.REJECTED: {ContentStatus.DRAFT, ContentStatus.ARCHIVED},
    ContentStatus.ARCHIVED: set(),
}


class PublicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SENDING = "SENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class BatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    SUCCESS = "SUCCESS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"


class AutopilotMode(str, enum.Enum):
    MANUAL = "MANUAL"
    APPROVAL = "APPROVAL"
    AUTOPILOT = "AUTOPILOT"


class JobType(str, enum.Enum):
    AI_GENERATE_POST = "AI_GENERATE_POST"
    AI_REWRITE_POST = "AI_REWRITE_POST"  # legacy v0.1 value, kept so the PG enum stays compatible
    AI_REWRITE = "AI_REWRITE"
    AI_GENERATE_IMAGE = "AI_GENERATE_IMAGE"
    TELEGRAM_PUBLISH = "TELEGRAM_PUBLISH"
    TELEGRAM_RETRY = "TELEGRAM_RETRY"
    TELEGRAM_REFRESH_CHANNELS = "TELEGRAM_REFRESH_CHANNELS"
    TELEGRAM_REFRESH_METRICS = "TELEGRAM_REFRESH_METRICS"
    SOURCE_FETCH = "SOURCE_FETCH"
    AUTOPILOT_PLAN = "AUTOPILOT_PLAN"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IdeaStatus(str, enum.Enum):
    NEW = "NEW"
    SHORTLISTED = "SHORTLISTED"
    USED = "USED"
    DISMISSED = "DISMISSED"


class MediaStatus(str, enum.Enum):
    GENERATED = "GENERATED"
    UPLOADED = "UPLOADED"
    USED = "USED"
    UNUSED = "UNUSED"
    ARCHIVED = "ARCHIVED"


class AIOperation(str, enum.Enum):
    GENERATE_POST = "GENERATE_POST"
    REWRITE = "REWRITE"
    SHORTEN = "SHORTEN"
    EXPAND = "EXPAND"
    CHANGE_TONE = "CHANGE_TONE"
    REGENERATE_TITLE = "REGENERATE_TITLE"
    REGENERATE_FRAGMENT = "REGENERATE_FRAGMENT"
    GENERATE_IMAGE_PROMPT = "GENERATE_IMAGE_PROMPT"
    GENERATE_IMAGE = "GENERATE_IMAGE"
    IMPROVE = "IMPROVE"
    GENERATE_CTA = "GENERATE_CTA"
    REMOVE_CLICHES = "REMOVE_CLICHES"


class AIRequestStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRIED = "RETRIED"


class ImageProviderStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
