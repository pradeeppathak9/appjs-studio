package com.appjs.restyle.data

import android.content.Context
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

/** The signed-in person. Exactly one of [email] / [phone] identifies them. */
data class User(
    val id: String,
    val name: String?,
    val email: String?,
    val phone: String?,
    val photoUrl: String?,
) {
    val initials: String
        get() {
            val parts = name.orEmpty().trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
            return when {
                parts.size >= 2 -> "${parts.first().first()}${parts.last().first()}".uppercase()
                parts.size == 1 -> parts.first().take(2).uppercase()
                !email.isNullOrBlank() -> email.take(1).uppercase()
                else -> ""
            }
        }
}

sealed interface GoogleSignInResult {
    /** [idToken] is sent to AppJs Studio, which verifies it and signs the user in. */
    data class Success(val idToken: String) : GoogleSignInResult
    data object Cancelled : GoogleSignInResult
    data class Failed(val message: String) : GoogleSignInResult
}

/**
 * Google Sign-In through Android Credential Manager: gets a Google ID token for [clientId] (the
 * OAuth *Web* client id the server lists in GET /v1/app), which the server then verifies.
 */
class GoogleAuth {
    /** [activityContext] must be an Activity: the account picker is shown over it. */
    suspend fun signIn(activityContext: Context, clientId: String): GoogleSignInResult {
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(GetSignInWithGoogleOption.Builder(clientId).build())
            .build()

        return try {
            val credential = CredentialManager.create(activityContext).getCredential(activityContext, request).credential
            if (credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                val google = GoogleIdTokenCredential.createFrom(credential.data)
                GoogleSignInResult.Success(google.idToken)
            } else {
                GoogleSignInResult.Failed("Unexpected sign-in response. Try again.")
            }
        } catch (_: GetCredentialCancellationException) {
            GoogleSignInResult.Cancelled
        } catch (_: NoCredentialException) {
            GoogleSignInResult.Failed("No Google account found on this phone. Add one in Settings, or use your phone number.")
        } catch (e: GetCredentialException) {
            GoogleSignInResult.Failed("Google sign-in didn't work. Try again.")
        }
    }

    /** Clears the remembered account so the picker shows again next time. */
    suspend fun signOut(context: Context) {
        runCatching { CredentialManager.create(context).clearCredentialState(ClearCredentialStateRequest()) }
    }
}
