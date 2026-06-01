resource "random_password" "db" {
  length           = 24
  special          = true
  override_special = "!#$%&*()-_=+[]{}|:,.<>?"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "aws_secretsmanager_secret" "this" {
  name        = "pickup/${var.environment}/app-secrets"
  description = "Application secrets for PickUp AI ${var.environment} environment"

  tags = {
    Name = "pickup-${var.environment}-secrets"
  }
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode(merge(
    {
      TWILIO_ACCOUNT_SID    = ""
      TWILIO_AUTH_TOKEN     = ""
      TWILIO_API_KEY_SID    = ""
      TWILIO_API_KEY_SECRET = ""
      TWILIO_TWIML_APP_SID  = ""
      TWILIO_VERIFY_SID     = ""
      OPENAI_API_KEY        = ""
      RESEND_API_KEY        = ""
      RESEND_FROM           = ""
      ELEVENLABS_API_KEY    = ""
      GOOGLE_TTS_API_KEY    = ""
      ADMIN_PASSWORD        = ""
      SECRET_KEY            = ""
      DATABASE_URL          = ""
    },
    var.secret_values,
    {
      DB_PASSWORD = random_password.db.result
    }
  ))

  lifecycle {
    ignore_changes = [secret_string]
  }
}
